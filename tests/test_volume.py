import math

import pytest

from botnik.volume import ROUNDISH_FACTOR, estimate, soil_surface_cm2


def test_round():
    # outer Ø30 × 22 -> inner Ø28, depth 21
    e = estimate("round", diameter=30, height=22)
    assert e.surface_cm2 == pytest.approx(math.pi * 28**2 / 4)
    assert e.volume_l == pytest.approx(math.pi * 28**2 / 4 * 21 / 1000)
    assert 12 < e.volume_l < 13


def test_rectangular():
    # outer 57 × 20 × 14 -> inner 55 × 18 × 13
    e = estimate("rectangular", length=57, width=20, height=14)
    assert e.surface_cm2 == pytest.approx(55 * 18)
    assert e.volume_l == pytest.approx(55 * 18 * 13 / 1000)


def test_elliptical():
    # outer 60 × 20 × 25 -> inner axes 58 × 18, depth 24
    e = estimate("elliptical", length=60, width=20, height=25)
    assert e.surface_cm2 == pytest.approx(math.pi * 58 * 18 / 4)
    assert e.volume_l == pytest.approx(math.pi * 58 * 18 / 4 * 24 / 1000)


def test_elliptical_unknown_width_is_none():
    # The large red railing planters: width not measured yet.
    assert estimate("elliptical", length=60, width=None, height=25) is None
    assert soil_surface_cm2("elliptical", length=60, width=None) is None


def test_roundish_is_between_circle_and_square():
    e = estimate("roundish", diameter=30, height=25)
    assert e.surface_cm2 == pytest.approx(ROUNDISH_FACTOR * 28**2)
    assert math.pi * 28**2 / 4 < e.surface_cm2 < 28**2


@pytest.mark.parametrize(
    "shape, kwargs",
    [
        ("round", {"diameter": None, "height": 20}),
        ("round", {"diameter": 20, "height": None}),
        ("rectangular", {"length": 40, "width": None, "height": 15}),
        (None, {"diameter": 20, "height": 20}),
        ("hexagonal", {"diameter": 20, "height": 20}),
        ("round", {"diameter": 1, "height": 20}),  # nothing left after the walls
    ],
)
def test_missing_or_unknown_returns_none(shape, kwargs):
    assert estimate(shape, **kwargs) is None
