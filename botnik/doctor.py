"""Pest issues in the database: open, treat step by step, follow up, resolve."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from botnik import carelog, clock
from botnik.models import Container, Issue, Plant, Task
from botnik.pests import PESTS, product
from botnik.treatment import EDIBLE_GROUPS, Plan, Step, confidor_refusal, plan_for, start_step

REPEAT_WINDOW_DAYS = 90
EVENING_HOUR = 17  # neem before this local hour gets a reminder about sun and heat
ACTIVE = ("open", "postponed")


def is_edible(container: Container) -> bool:
    """Edible plants and herbs, including shared soil: one edible plant in the pot counts for all."""
    return any(p.feed_group in EDIBLE_GROUPS for p in container.plants)


def is_sensitive(container: Container, plant: Plant | None) -> bool:
    plants = [plant] if plant else container.plants
    return any(p.pest_profile == "sensitive" for p in plants)


def plan(issue: Issue) -> Plan:
    """The issue's plan, fixed by the track chosen when it was opened."""
    return plan_for(
        issue.pest, edible=issue.track == "edible", sensitive=issue.track == "sensitive", flowering=issue.flowering
    )


def current_step(issue: Issue) -> Step:
    steps = plan(issue).steps
    return steps[min(issue.step, len(steps) - 1)]


def _repeat(session: Session, container: Container, plant: Plant | None, pest: str, now: datetime) -> bool:
    since = now - timedelta(days=REPEAT_WINDOW_DAYS)
    query = select(Issue.id).where(Issue.container_id == container.id, Issue.pest == pest, Issue.opened_at >= since)
    if plant is not None:
        query = query.where((Issue.plant_id == plant.id) | (Issue.plant_id.is_(None)))
    return session.scalar(query) is not None


def open_issue(
    session: Session, container: Container, plant: Plant | None, pest: str, severity: str, flowering: bool
) -> tuple[Issue, str | None]:
    """Open an issue. Returns it and a note when the plant was moved to the sensitive track."""
    now = clock.now_utc()
    note = None
    if _repeat(session, container, plant, pest, now):
        for p in [plant] if plant else container.plants:
            p.pest_profile = "sensitive"
        note = f"{PESTS[pest].name_he} חזרה תוך {REPEAT_WINDOW_DAYS} יום – עבר למסלול הרגיש."
    edible = is_edible(container)
    track_plan = plan_for(pest, edible=edible, sensitive=is_sensitive(container, plant), flowering=flowering)
    issue = Issue(
        user_id=container.user_id, container_id=container.id, plant_id=plant.id if plant else None, pest=pest,
        severity=severity, flowering=flowering, track=track_plan.track, status="open",
        step=start_step(track_plan, severity), opened_at=now,
    )
    session.add(issue)
    session.commit()
    return issue, note


def _close_tasks(session: Session, issue: Issue, type: str | None = None, event_id: int | None = None) -> None:
    query = select(Task).where(Task.issue_id == issue.id, Task.status.in_(ACTIVE))
    if type:
        query = query.where(Task.type == type)
    for task in session.scalars(query):
        task.status, task.closed_at, task.care_event_id = "done", clock.now_utc(), event_id


def do_step(session: Session, issue: Issue, today: date, now_local_hour: int | None = None) -> tuple[bool, str]:
    """The owner did the current step. Returns (logged, message for the owner)."""
    step = current_step(issue)
    container = issue.container
    if step.product == "confidor":
        refusal = confidor_refusal(edible=is_edible(container), flowering=issue.flowering, pest_key=issue.pest)
        if refusal:
            return False, f"⛔ {refusal}"
    prod = product(session, issue.user_id, step.product)
    event = carelog.log(
        session, container, step.event_type, source="doctor", product_id=prod.id if prod else None,
        note=f"{PESTS[issue.pest].name_he}: {step.text_he}", commit=False,
    )
    event.plant_id = issue.plant_id
    issue.next_check = today + timedelta(days=step.check_days)
    _close_tasks(session, issue, "treat", event.id)
    session.commit()
    message = f"✅ נרשם. בדיקה ב־{issue.next_check:%d.%m}."
    hour = now_local_hour if now_local_hour is not None else datetime.now(timezone.utc).astimezone(clock.TZ).hour
    if step.product == "neem" and hour < EVENING_HOUR:
        message += "\n⚠️ נים מרססים רק בערב, לא בשמש ולא בחום – אם עוד לא ריססת, חכה לערב."
    return True, message


def remind_step(session: Session, issue: Issue, today: date) -> Task:
    """Put the current step in the daily messages (neem: evening summary only)."""
    existing = session.scalars(
        select(Task).where(Task.issue_id == issue.id, Task.type == "treat", Task.status.in_(ACTIVE))
    ).first()
    if existing:
        return existing
    step = current_step(issue)
    task = Task(
        user_id=issue.user_id, container_id=issue.container_id, type="treat", due_date=today, status="open",
        reason=step.text_he, created_at=clock.now_utc(), issue_id=issue.id, evening_only=step.evening_only,
    )
    session.add(task)
    session.commit()
    return task


def resolve(session: Session, issue: Issue) -> None:
    issue.status, issue.resolved_at, issue.next_check = "resolved", clock.now_utc(), None
    _close_tasks(session, issue)
    session.commit()


def check_result(session: Session, issue: Issue, result: str, today: date) -> str:
    """Follow-up answer: clean / less / worse. Returns a message for the owner."""
    _close_tasks(session, issue, "check")
    if result == "clean":
        resolve(session, issue)
        return f"✅ מעולה – {PESTS[issue.pest].name_he} ב־#{issue.container.number} נסגרה."
    steps = plan(issue).steps
    if result == "worse":
        issue.step = min(issue.step + 1, len(steps) - 1)
    issue.next_check = None
    session.commit()
    remind_step(session, issue, today)
    step = current_step(issue)
    head = "😐 חוזרים על אותו שלב." if result == "less" else f"➡️ עוברים לשלב {issue.step + 1}."
    when = "בסיכום הערב" if step.evening_only else "בתדריך"
    return f"{head} {step.text_he}\nזה יופיע {when}."


def delete_issue(session: Session, issue: Issue) -> None:
    """Opened by mistake: remove it and its reminders (logged treatments stay in the care log)."""
    session.execute(delete(Task).where(Task.issue_id == issue.id))
    session.delete(issue)
    session.commit()


def get(session: Session, user_id: int, issue_id: int) -> Issue | None:
    issue = session.get(Issue, issue_id)
    return issue if issue and issue.user_id == user_id else None


def open_issues(session: Session, user_id: int, container_id: int | None = None) -> list[Issue]:
    query = select(Issue).where(Issue.user_id == user_id, Issue.status == "open")
    if container_id is not None:
        query = query.where(Issue.container_id == container_id)
    return list(session.scalars(query.order_by(Issue.opened_at)))


def open_pests_by_container(session: Session, user_id: int) -> dict[int, set[str]]:
    out: dict[int, set[str]] = {}
    for issue in open_issues(session, user_id):
        out.setdefault(issue.container_id, set()).add(issue.pest)
    return out


def due_checks(session: Session, user_id: int, today: date) -> list[Issue]:
    return [i for i in open_issues(session, user_id) if i.next_check and i.next_check <= today]


def summary_he(issue: Issue) -> str:
    total = len(plan(issue).steps)
    check = f" · בדיקה ב־{issue.next_check:%d.%m}" if issue.next_check else " · ממתין לטיפול"
    who = f" ({issue.plant.name_he})" if issue.plant and len(issue.container.plants) > 1 else ""
    return f"{PESTS[issue.pest].name_he}{who} · שלב {min(issue.step, total - 1) + 1} מתוך {total}{check}"
