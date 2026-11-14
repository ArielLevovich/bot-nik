"""When to water and when to fertilize. Deterministic Phase-2 rules (no weather yet).

All numbers are starting values; the owner's taps tune watering per container
through container.water_adjust_days.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from botnik.care import WATER_NEED_HE
from botnik.sun import season_for
from botnik.volume import estimate_container

# Base watering interval in days, by season and the container's thirstiest plant.
WATER_BASE = {
    "winter": {"low": 14, "medium": 6, "high": 3},
    "summer": {"low": 10, "medium": 3, "high": 1},
}
NEED_RANK = {"low": 0, "medium": 1, "high": 2}
SMALL_POT_L, LARGE_POT_L = 3, 20
EXPOSED_LEVELS = ("railing", "railing_hanging", "hanging")
BREATHING_MATERIALS = ("terracotta", "fabric")
ADJUST_LIMIT = 0.5  # learned adjustment can move the interval by at most ±50%

AMOUNT_SHARE = 0.2  # suggested water ≈ 20% of the soil volume ...
MAX_AMOUNT_L = 10.0  # ... but never more than this at once (big-pot volumes are overestimated: no taper)

ADJUSTMENT_DAYS = 21  # no fertilizing after planting or a move
SUMMER_MONTHS = range(4, 10)  # Apr–Sep
GROWING_MONTHS = range(4, 11)  # Apr–Oct


@dataclass(frozen=True)
class Plan:
    days: int | None  # None = not now
    reason: str


def _round(x: float) -> int:
    return int(x + 0.5)


def water_interval(container, season: str) -> Plan | None:
    """Days between waterings, or None when no plant has a water need yet."""
    needs = [p.water_need for p in container.plants if p.water_need in NEED_RANK]
    if not needs:
        return None
    need = max(needs, key=NEED_RANK.__getitem__)
    days = float(WATER_BASE[season][need])
    reasons = [WATER_NEED_HE[need]]

    est = estimate_container(container)
    if est and est.volume_l < SMALL_POT_L:
        days *= 0.7
        reasons.append("עציץ קטן")
    elif est and est.volume_l > LARGE_POT_L:
        days *= 1.3
        reasons.append("עציץ גדול")
    if container.material in BREATHING_MATERIALS:
        days *= 0.8
        reasons.append("חומר נושם")
    if container.level in EXPOSED_LEVELS:
        days *= 0.8
        reasons.append("חשוף לשמש ולרוח")

    adjust = container.water_adjust_days or 0
    limit = days * ADJUST_LIMIT
    adjust = max(-limit, min(limit, adjust))
    if adjust:
        reasons.append("כוונון לפי הדיווחים שלך")
    return Plan(max(1, _round(days + adjust)), ", ".join(reasons))


def suggested_amount_l(container) -> float | None:
    est = estimate_container(container)
    if not est:
        return None
    return min(MAX_AMOUNT_L, max(0.1, round(est.volume_l * AMOUNT_SHARE, 1)))


def feed_days_for_group(group: str | None, month: int) -> int | None:
    if group == "flowering":
        return 14 if month in GROWING_MONTHS else 28
    if group == "edible":
        return 14 if month in GROWING_MONTHS else None
    if group == "herb":
        return 28 if month in SUMMER_MONTHS else None
    if group == "succulent":
        return 56 if month in SUMMER_MONTHS else None
    if group == "foliage":
        return 21 if month in GROWING_MONTHS else None
    return None


def adjustment_ends(container, last_move: date | None) -> date | None:
    """End of the no-fertilizing period after the latest planting or move, if any."""
    starts = [p.planted_on for p in container.plants if p.planted_on] + ([last_move] if last_move else [])
    if not starts:
        return None
    return max(starts) + timedelta(days=ADJUSTMENT_DAYS)


def feed_interval(container, day: date) -> Plan:
    groups = [p.feed_group for p in container.plants if p.feed_group]
    if not groups:
        return Plan(None, "חסר סוג דישון")
    intervals = [d for d in (feed_days_for_group(g, day.month) for g in groups) if d]
    if not intervals:
        return Plan(None, "לא מדשנים בעונה הזו")
    return Plan(min(intervals), "לפי העונה וסוג הצמח")


def next_water(container, last: date | None, today: date) -> tuple[date | None, Plan | None]:
    plan = water_interval(container, season_for(today))
    if plan is None:
        return None, None
    return (today if last is None else last + timedelta(days=plan.days)), plan


def next_feed(container, last: date | None, today: date, last_move: date | None = None) -> tuple[date | None, Plan]:
    if container.status == "needs_care":
        return None, Plan(None, "במצוקה (🔴) – לא מדשנים עד שמשתפר")
    plan = feed_interval(container, today)
    if plan.days is None:
        return None, plan
    due = today if last is None else last + timedelta(days=plan.days)
    ends = adjustment_ends(container, last_move)
    if ends and ends > due:
        return ends, Plan(plan.days, f"תקופת הסתגלות עד {ends:%d.%m}")
    return due, plan
