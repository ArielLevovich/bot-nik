"""Sun hours per balcony area and season (data only; used by the smart model in Phase 4)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from botnik import labels as L
from botnik.models import AreaSun, Slot

SEASON_HE = {"winter": "חורף", "summer": "קיץ"}
WINTER_MONTHS = {10, 11, 12, 1, 2, 3}  # low sun, Oct-Mar; Apr-Sep counts as summer

FROM_HOURS = list(range(5, 15))  # 05..14
LAST_HOUR = 17


def season_for(day: date | None = None) -> str:
    return "winter" if (day or date.today()).month in WINTER_MONTHS else "summer"


def areas(session: Session, user_id: int) -> list[str]:
    """The owner's areas in map order."""
    seen: list[str] = []
    for slot in session.scalars(select(Slot).where(Slot.user_id == user_id).order_by(Slot.id)):
        if slot.area not in seen:
            seen.append(slot.area)
    return seen


def get(session: Session, user_id: int, area: str, season: str) -> AreaSun | None:
    return session.scalars(
        select(AreaSun).where(AreaSun.user_id == user_id, AreaSun.area == area, AreaSun.season == season)
    ).one_or_none()


def is_answered(row: AreaSun | None) -> bool:
    return row is not None and row.morning_sun is not None and row.afternoon_sun is not None


def unanswered(session: Session, user_id: int, season: str) -> list[str]:
    return [a for a in areas(session, user_id) if not is_answered(get(session, user_id, a, season))]


def save(
    session: Session,
    user_id: int,
    area: str,
    season: str,
    *,
    morning_from: int | None,
    morning_to: int | None,
    afternoon_sun: bool,
) -> AreaSun:
    """Save one area's answer. morning_from=None means no morning sun."""
    if morning_from is not None and (morning_to is None or morning_to <= morning_from):
        raise ValueError("morning_to must be after morning_from")
    row = get(session, user_id, area, season)
    if row is None:
        row = AreaSun(user_id=user_id, area=area, season=season)
        session.add(row)
    row.morning_sun = morning_from is not None
    row.morning_from = morning_from
    row.morning_to = morning_to if morning_from is not None else None
    row.afternoon_sun = afternoon_sun
    session.commit()
    return row


def describe(row: AreaSun | None) -> str:
    """Short Hebrew text, e.g. 'בוקר 07:00–12:00 · אחה״צ: אין'."""
    if not is_answered(row):
        return "עוד לא נרשם"
    morning = f"בוקר {row.morning_from:02d}:00–{row.morning_to:02d}:00" if row.morning_sun else "אין שמש בבוקר"
    return f"{morning} · אחה״צ: {'יש' if row.afternoon_sun else 'אין'}"


def area_label(area: str) -> str:
    return L.he(L.AREA_HE, area)
