"""Reminders: create today's water/feed tasks from the rules, and act on the owner's taps."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from botnik import carelog, clock, rules
from botnik.care import fertilizers
from botnik.models import Container, Slot, Task

TYPES = ("water", "feed")
ACTIVE = ("open", "postponed")
FEED_SKIP_DAYS = 7  # after "not needed" on fertilizing, don't ask again for a week


def containers_in_map_order(session: Session, user_id: int) -> list[Container]:
    rows = session.execute(
        select(Container, Slot.id)
        .outerjoin(Slot, Container.slot_id == Slot.id)
        .where(Container.user_id == user_id)
    ).all()
    rows.sort(key=lambda r: (r[1] is None, r[1] or 0, r[0].number))
    return [c for c, _ in rows]


@dataclass
class Due:
    container: Container
    type: str
    due: date | None
    plan: rules.Plan | None


def due_dates(session: Session, user_id: int, today: date) -> list[Due]:
    last_water = carelog.last_dates(session, user_id, "water")
    last_feed = carelog.last_dates(session, user_id, "feed")
    last_move = carelog.last_dates(session, user_id, "move")
    out = []
    for c in containers_in_map_order(session, user_id):
        due, plan = rules.next_water(c, last_water.get(c.id), today)
        out.append(Due(c, "water", due, plan))
        due, plan = rules.next_feed(c, last_feed.get(c.id), today, last_move.get(c.id))
        out.append(Due(c, "feed", due, plan))
    return out


def _recently_skipped(session: Session, container_id: int, type: str, today: date) -> bool:
    days = 1 if type == "water" else FEED_SKIP_DAYS
    for task in session.scalars(
        select(Task).where(Task.container_id == container_id, Task.type == type, Task.status == "not_needed")
    ):
        if task.closed_at and (today - clock.local_date(task.closed_at)).days < days:
            return True
    return False


def generate(session: Session, user_id: int, today: date) -> list[Task]:
    """Create a task for every container that is due by today and has no active task. Returns new tasks."""
    active = {
        (t.container_id, t.type)
        for t in session.scalars(select(Task).where(Task.user_id == user_id, Task.status.in_(ACTIVE)))
    }
    created = []
    for d in due_dates(session, user_id, today):
        if d.due is None or d.due > today or (d.container.id, d.type) in active:
            continue
        if _recently_skipped(session, d.container.id, d.type, today):
            continue
        task = Task(
            user_id=user_id, container_id=d.container.id, type=d.type, due_date=today, status="open",
            reason=d.plan.reason if d.plan else None, created_at=clock.now_utc(),
        )
        session.add(task)
        created.append(task)
    session.commit()
    return created


def _order(session: Session, user_id: int) -> dict[int, int]:
    return {c.id: i for i, c in enumerate(containers_in_map_order(session, user_id))}


def actionable(session: Session, user_id: int, today: date) -> list[Task]:
    tasks = list(
        session.scalars(
            select(Task).where(Task.user_id == user_id, Task.status.in_(ACTIVE), Task.due_date <= today)
        )
    )
    order = _order(session, user_id)
    return sorted(tasks, key=lambda t: (order.get(t.container_id, 999), TYPES.index(t.type)))


def handled_today(session: Session, user_id: int, today: date) -> list[Task]:
    """Tasks the owner already acted on today (shown ticked in the brief)."""
    tasks = [
        t
        for t in session.scalars(select(Task).where(Task.user_id == user_id, Task.closed_at.is_not(None)))
        if clock.local_date(t.closed_at) == today and not (t.status in ACTIVE and t.due_date <= today)
    ]
    order = _order(session, user_id)
    return sorted(tasks, key=lambda t: (order.get(t.container_id, 999), TYPES.index(t.type)))


def get(session: Session, user_id: int, task_id: int) -> Task | None:
    task = session.get(Task, task_id)
    return task if task and task.user_id == user_id else None


def complete(session: Session, task: Task) -> None:
    if task.status not in ACTIVE:
        return
    c = task.container
    if task.type == "water":
        carelog.log(session, c, "water", source="task", amount_l=rules.suggested_amount_l(c), commit=False)
    else:
        products = fertilizers(session, c.user_id)
        carelog.log(session, c, "feed", source="task", product_id=products[0].id if products else None, commit=False)
    session.commit()  # carelog.log closed the task and linked the event


def postpone(session: Session, task: Task, today: date) -> None:
    if task.status not in ACTIVE:
        return
    task.status = "postponed"
    task.due_date = today + timedelta(days=1)
    task.closed_at = clock.now_utc()
    session.commit()


def not_needed(session: Session, task: Task) -> None:
    if task.status not in ACTIVE:
        return
    task.status = "not_needed"
    task.closed_at = clock.now_utc()
    if task.type == "water":
        task.container.water_adjust_days = (task.container.water_adjust_days or 0) + 1
    session.commit()


def report_dry(session: Session, container: Container, today: date) -> None:
    """Owner says a pot looks dry: water it sooner from now on, and today."""
    container.water_adjust_days = (container.water_adjust_days or 0) - 1
    carelog.log(session, container, "note", source="button", note="נראה יבש", commit=False)
    has_active = session.scalar(
        select(Task.id).where(Task.container_id == container.id, Task.type == "water", Task.status.in_(ACTIVE))
    )
    if not has_active:
        session.add(Task(
            user_id=container.user_id, container_id=container.id, type="water", due_date=today, status="open",
            reason="דיווחת שנראה יבש", created_at=clock.now_utc(),
        ))
    session.commit()


def tomorrow(session: Session, user_id: int, today: date) -> list[tuple[Container, str]]:
    """What is expected tomorrow: rule-based due dates plus postponed tasks."""
    nxt = today + timedelta(days=1)
    out = [(d.container, d.type) for d in due_dates(session, user_id, today) if d.due == nxt]
    for t in session.scalars(select(Task).where(Task.user_id == user_id, Task.status.in_(ACTIVE), Task.due_date == nxt)):
        if (t.container, t.type) not in out:
            out.append((t.container, t.type))
    return out
