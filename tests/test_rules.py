from datetime import date
from types import SimpleNamespace

import pytest

from botnik import rules
from botnik.care import CATALOG, catalog_defaults, genus


def plant(need="medium", group="flowering", planted_on=None):
    return SimpleNamespace(water_need=need, feed_group=group, planted_on=planted_on)


def pot(*plants, shape="rectangular", length=40, width=20, height=16, diameter=None, material="plastic", level="shelf",
        adjust=None, status="good"):
    return SimpleNamespace(
        plants=list(plants) or [plant()], shape=shape, outer_length_cm=length, outer_width_cm=width,
        outer_height_cm=height, outer_diameter_cm=diameter, material=material, level=level,
        water_adjust_days=adjust, status=status,
    )


WINTER, SUMMER = date(2026, 11, 20), date(2027, 7, 10)


# --- catalog ---

def test_genus_parsing():
    assert genus("Pelargonium × hortorum") == "pelargonium"
    assert genus("Ocimum × hybrid ('Magic Mountain'?)") == "ocimum"
    assert genus("Hoya sp.") == "hoya"
    assert genus(None) is None


def test_catalog_values_are_valid():
    for need, group in CATALOG.values():
        assert need in rules.NEED_RANK and rules.feed_days_for_group(group, 6) is not None
    assert catalog_defaults("Aloe vera") == ("low", "succulent")
    assert catalog_defaults("Unknownus plantus") is None


# --- watering ---

@pytest.mark.parametrize("season, need, days", [
    ("winter", "low", 14), ("winter", "medium", 6), ("winter", "high", 3),
    ("summer", "low", 10), ("summer", "medium", 3), ("summer", "high", 1),
])
def test_base_intervals(season, need, days):
    # 40×20×16 plastic on a shelf = ~10 L: no pot factors
    assert rules.water_interval(pot(plant(need)), season).days == days


def test_thirstiest_plant_decides_shared_soil():
    assert rules.water_interval(pot(plant("low"), plant("high")), "winter").days == 3


def test_small_pot_dries_faster():
    small = pot(plant("medium"), shape="round", diameter=12, height=10)  # ~0.7 L
    assert rules.water_interval(small, "winter").days == 4  # 6 × 0.7 = 4.2
    assert "עציץ קטן" in rules.water_interval(small, "winter").reason


def test_large_pot_holds_longer():
    big = pot(plant("medium"), shape="round", diameter=56, height=54)  # ~120 L
    assert rules.water_interval(big, "winter").days == 8  # 6 × 1.3 = 7.8


def test_exposed_and_breathing_pots():
    p = pot(plant("medium"), material="terracotta", level="railing")
    assert rules.water_interval(p, "winter").days == 4  # 6 × 0.8 × 0.8 = 3.84


def test_unknown_volume_has_no_pot_factor():
    assert rules.water_interval(pot(plant("medium"), width=None), "winter").days == 6


def test_learned_adjustment_is_limited():
    assert rules.water_interval(pot(plant("medium"), adjust=2), "winter").days == 8
    assert rules.water_interval(pot(plant("medium"), adjust=10), "winter").days == 9  # +50% max
    assert rules.water_interval(pot(plant("medium"), adjust=-10), "winter").days == 3  # -50% max
    assert rules.water_interval(pot(plant("high"), adjust=-10), "summer").days == 1  # never below 1


def test_no_profile_means_no_plan():
    assert rules.water_interval(pot(plant(None, None)), "winter") is None


def test_next_water():
    p = pot(plant("medium"))
    assert rules.next_water(p, None, WINTER)[0] == WINTER  # no history: due now
    assert rules.next_water(p, date(2026, 11, 18), WINTER)[0] == date(2026, 11, 24)


def test_suggested_amount():
    assert rules.suggested_amount_l(pot()) == 2.1  # inner 38×18×15 = 10.26 L × 20% = 2.05
    assert rules.suggested_amount_l(pot(width=None)) is None
    big = pot(shape="round", diameter=56, height=54)  # ~120 L estimate
    assert rules.suggested_amount_l(big) == rules.MAX_AMOUNT_L


# --- fertilizing ---

@pytest.mark.parametrize("group, month, days", [
    ("flowering", 6, 14), ("flowering", 12, 28),
    ("edible", 5, 14), ("edible", 12, None),
    ("herb", 7, 28), ("herb", 10, None), ("herb", 12, None),
    ("succulent", 7, 56), ("succulent", 11, None),
    ("foliage", 10, 21), ("foliage", 11, None),
    (None, 6, None),
])
def test_feed_by_group_and_month(group, month, days):
    assert rules.feed_days_for_group(group, month) == days


def test_feed_uses_shortest_interval_and_explains_winter_pause():
    assert rules.feed_interval(pot(plant(group="herb"), plant(group="flowering")), WINTER).days == 28
    assert rules.feed_interval(pot(plant(group="herb")), WINTER) == rules.Plan(None, "לא מדשנים בעונה הזו")


def test_no_feeding_in_distress():
    due, plan = rules.next_feed(pot(plant(group="flowering"), status="needs_care"), None, WINTER)
    assert due is None and "מצוקה" in plan.reason


def test_adjustment_period_after_planting_or_move():
    planted = pot(plant(group="flowering", planted_on=date(2026, 11, 10)))
    due, plan = rules.next_feed(planted, None, WINTER)
    assert due == date(2026, 12, 1) and "הסתגלות" in plan.reason
    moved = pot(plant(group="flowering"))
    due, _ = rules.next_feed(moved, date(2026, 10, 1), WINTER, last_move=date(2026, 11, 15))
    assert due == date(2026, 12, 6)
    old = pot(plant(group="flowering", planted_on=date(2026, 1, 1)))
    assert rules.next_feed(old, date(2026, 11, 1), WINTER)[0] == date(2026, 11, 29)
