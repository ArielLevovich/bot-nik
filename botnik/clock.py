"""Time helpers. The database stores naive UTC; the owner lives in Israel time."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Jerusalem")
WEEKDAY_HE = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]  # date.weekday(): Monday = 0


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def today() -> date:
    return datetime.now(TZ).date()


def local_date(utc_naive: datetime) -> date:
    return utc_naive.replace(tzinfo=timezone.utc).astimezone(TZ).date()


def utc_at_local(day: date, hour: int = 8) -> datetime:
    """Naive UTC for a local wall-clock time on `day` (used to back-date events)."""
    return datetime.combine(day, time(hour), TZ).astimezone(timezone.utc).replace(tzinfo=None)


def days_ago(day: date, ref: date) -> int:
    return (ref - day).days


def ago_he(day: date | None, ref: date) -> str:
    if day is None:
        return "לא נרשם"
    n = days_ago(day, ref)
    if n <= 0:
        return "היום"
    if n == 1:
        return "אתמול"
    return f"לפני {n} ימים"


def when_he(day: date | None, ref: date) -> str:
    if day is None:
        return "—"
    n = (day - ref).days
    if n < 0:
        return "באיחור" if n < -1 else "היה צריך אתמול"
    if n == 0:
        return "היום"
    if n == 1:
        return "מחר"
    return f"בעוד {n} ימים ({day:%d.%m})"


def date_he(day: date) -> str:
    return f"יום {WEEKDAY_HE[day.weekday()]} {day:%d.%m}"


def parse_hhmm(value: str) -> time:
    h, m = value.split(":")
    return time(int(h), int(m), tzinfo=TZ)


def plus_days(day: date, n: int) -> date:
    return day + timedelta(days=n)
