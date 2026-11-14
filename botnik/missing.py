"""What is still missing for a container, computed from its fields.

Core fields are derived from what is None, so the list can never get out of date.
Things that can't be derived (e.g. "what does 10 × 12 mean?") live in
`container.missing_extra` and are added after the core fields.

The order of the returned keys is the order the bot asks the questions in.
"""

from __future__ import annotations

# Dimension fields each shape needs, in asking order.
SHAPE_DIMENSIONS: dict[str, tuple[str, ...]] = {
    "round": ("outer.diameter", "outer.height"),
    "roundish": ("outer.diameter", "outer.height"),
    "rectangular": ("outer.length", "outer.width", "outer.height"),
    "elliptical": ("outer.length", "outer.width", "outer.height"),
}

# missing key -> Container attribute
FIELD_ATTR: dict[str, str] = {
    "slot": "slot_id",
    "level": "level",
    "shape": "shape",
    "outer.diameter": "outer_diameter_cm",
    "outer.length": "outer_length_cm",
    "outer.width": "outer_width_cm",
    "outer.height": "outer_height_cm",
    "material": "material",
    "color": "color",
    "condition": "condition",
}

# Placeholder shown while the shape is unknown: which dimensions are needed depends on it.
DIMENSIONS_UNKNOWN_SHAPE = "outer"


def _is_core(key: str) -> bool:
    return key in FIELD_ATTR or key == DIMENSIONS_UNKNOWN_SHAPE or key.startswith("outer.")


def missing_fields(container) -> list[str]:
    missing: list[str] = []
    for key in ("slot", "level", "shape"):
        if getattr(container, FIELD_ATTR[key]) is None:
            missing.append(key)

    dims = SHAPE_DIMENSIONS.get(container.shape) if container.shape else None
    if dims is None:
        if container.shape is None:
            missing.append(DIMENSIONS_UNKNOWN_SHAPE)
    else:
        missing += [d for d in dims if getattr(container, FIELD_ATTR[d]) is None]

    for key in ("material", "color", "condition"):
        value = getattr(container, FIELD_ATTR[key])
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(key)

    # Hand-written extras; any that duplicate a core field are ignored (core is computed).
    missing += [m for m in (container.missing_extra or []) if not _is_core(m) and m not in missing]
    return missing


def extras_from_yaml(keys: list[str]) -> list[str]:
    """Keep only the YAML `missing` items that can't be computed from the fields."""
    return [str(k) for k in keys if not _is_core(str(k))]
