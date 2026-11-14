"""The care log: what was done to which container, and undo."""

from __future__ import annotations

import secrets
from datetime import date, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from botnik import clock
from botnik.models import CareEvent, Container, Slot, Task

BASELINE_UNKNOWN = "baseline:unknown"  # note marking "owner doesn't remember" for an area


def new_batch() -> str:
    return secrets.token_hex(4)


def log(
    session: Session,
    container: Container,
    type: str,
    *,
    source: str,
    batch: str | None = None,
    amount_l: float | None = None,
    product_id: int | None = None,
    at: datetime | None = None,
    note: str | None = None,
    commit: bool = True,
) -> CareEvent:
    event = CareEvent(
        user_id=container.user_id,
        container_id=container.id,
        type=type,
        amount_l=amount_l,
        product_id=product_id,
        at=at or clock.now_utc(),
        source=source,
        note=note,
        batch=batch or new_batch(),
    )
    session.add(event)
    session.flush()
    if type in ("water", "feed"):
        close_open_tasks(session, container, type, event)
    if commit:
        session.commit()
    return event


def close_open_tasks(session: Session, container: Container, type: str, event: CareEvent) -> None:
    """Logging water/feed by hand also ticks off any open reminder for it."""
    for task in session.scalars(
        select(Task).where(Task.container_id == container.id, Task.type == type, Task.status.in_(("open", "postponed")))
    ):
        task.status = "done"
        task.closed_at = event.at
        task.care_event_id = event.id


def undo_batch(session: Session, user_id: int, batch: str) -> int:
    events = list(session.scalars(select(CareEvent).where(CareEvent.user_id == user_id, CareEvent.batch == batch)))
    if not events:
        return 0
    ids = [e.id for e in events]
    for task in session.scalars(select(Task).where(Task.care_event_id.in_(ids))):
        task.status, task.closed_at, task.care_event_id = "open", None, None
    session.execute(delete(CareEvent).where(CareEvent.id.in_(ids)))
    session.commit()
    return len(ids)


def last_dates(session: Session, user_id: int, type: str) -> dict[int, date]:
    """container id -> local date of the latest event of this type."""
    rows = session.execute(
        select(CareEvent.container_id, func.max(CareEvent.at))
        .where(CareEvent.user_id == user_id, CareEvent.type == type)
        .group_by(CareEvent.container_id)
    )
    return {cid: clock.local_date(at) for cid, at in rows}


def last_date(session: Session, container_id: int, type: str) -> date | None:
    at = session.scalar(select(func.max(CareEvent.at)).where(CareEvent.container_id == container_id, CareEvent.type == type))
    return clock.local_date(at) if at else None


def areas_without_history(session: Session, user_id: int, type: str) -> list[str]:
    """Areas where no container has any event of this type (or an "I don't remember" answer)."""
    answered = set(
        session.scalars(
            select(Slot.area)
            .join(Container, Container.slot_id == Slot.id)
            .join(CareEvent, CareEvent.container_id == Container.id)
            .where(
                Container.user_id == user_id,
                (CareEvent.type == type) | (CareEvent.note == f"{BASELINE_UNKNOWN}:{type}"),
            )
        )
    )
    from botnik.sun import areas  # map order

    with_containers = set(
        session.scalars(select(Slot.area).join(Container, Container.slot_id == Slot.id).where(Container.user_id == user_id))
    )
    return [a for a in areas(session, user_id) if a in with_containers and a not in answered]
