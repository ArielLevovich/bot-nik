"""Estimate inner soil volume and surface from outer container dimensions.

Deterministic, no guessing: if a needed dimension is missing, return None.

Assumptions (outer cm, measured with the plant inside):
- Walls are ~1 cm thick: subtract 2 cm from each horizontal dimension and 1 cm
  from the height (the bottom).
- Sides are straight (no taper correction yet).
- "roundish" (e.g. the small red railing planters) is between a circle and a
  square of the same diameter: area factor = (pi/4 + 1) / 2 ~= 0.89.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

WALL_CM = 1.0
ROUNDISH_FACTOR = (math.pi / 4 + 1) / 2


@dataclass(frozen=True)
class Estimate:
    surface_cm2: float
    volume_l: float


def _inner(outer: float | None) -> float | None:
    if outer is None:
        return None
    inner = outer - 2 * WALL_CM
    return inner if inner > 0 else None


def soil_surface_cm2(
    shape: str | None,
    *,
    length: float | None = None,
    width: float | None = None,
    diameter: float | None = None,
) -> float | None:
    """Inner soil surface in cm², or None if the shape or a dimension is unknown."""
    if shape == "round":
        d = _inner(diameter)
        return None if d is None else math.pi * d * d / 4
    if shape == "roundish":
        d = _inner(diameter)
        return None if d is None else ROUNDISH_FACTOR * d * d
    if shape == "rectangular":
        l, w = _inner(length), _inner(width)
        return None if l is None or w is None else l * w
    if shape == "elliptical":
        l, w = _inner(length), _inner(width)
        return None if l is None or w is None else math.pi * l * w / 4
    return None


def estimate(
    shape: str | None,
    *,
    height: float | None,
    length: float | None = None,
    width: float | None = None,
    diameter: float | None = None,
) -> Estimate | None:
    """Inner surface (cm²) and volume (L), or None if anything needed is missing."""
    surface = soil_surface_cm2(shape, length=length, width=width, diameter=diameter)
    if surface is None or height is None:
        return None
    depth = height - WALL_CM
    if depth <= 0:
        return None
    return Estimate(surface_cm2=surface, volume_l=surface * depth / 1000)


def estimate_container(container) -> Estimate | None:
    """Convenience wrapper for a models.Container."""
    return estimate(
        container.shape,
        height=container.outer_height_cm,
        length=container.outer_length_cm,
        width=container.outer_width_cm,
        diameter=container.outer_diameter_cm,
    )
