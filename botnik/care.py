"""Care profile per plant: how thirsty it is and how it is fed.

Defaults come from a small catalog by Latin genus. They are starting values the owner
reviews in /care; anything the catalog doesn't know stays None and shows up in /missing.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from botnik.models import Plant, Product

WATER_NEEDS = ["low", "medium", "high"]
FEED_GROUPS = ["flowering", "edible", "herb", "succulent", "foliage"]

WATER_NEED_HE = {"low": "מעט מים", "medium": "בינוני", "high": "הרבה מים"}
WATER_NEED_BUTTON = {
    "low": "💧 מעט (סוקולנט, תבלין ים־תיכוני)",
    "medium": "💧💧 בינוני",
    "high": "💧💧💧 הרבה (עלים רכים, בזיליקום)",
}
FEED_GROUP_HE = {
    "flowering": "פורח",
    "edible": "צמח מאכל",
    "herb": "תבלין",
    "succulent": "סוקולנט",
    "foliage": "צמח עלים",
}

# genus -> (water_need, feed_group)
CATALOG: dict[str, tuple[str, str]] = {
    "aloe": ("low", "succulent"),
    "artemisia": ("low", "herb"),
    "brassica": ("high", "edible"),
    "chrysanthemum": ("medium", "flowering"),
    "cyclamen": ("medium", "flowering"),
    "dichondra": ("medium", "foliage"),
    "exacum": ("medium", "flowering"),
    "hoya": ("low", "foliage"),
    "ipomoea": ("high", "foliage"),
    "lavandula": ("low", "herb"),
    "lobularia": ("medium", "flowering"),
    "matthiola": ("medium", "flowering"),
    "melissa": ("medium", "herb"),
    "ocimum": ("high", "edible"),
    "oxalis": ("medium", "flowering"),
    "pelargonium": ("medium", "flowering"),
    "ruta": ("low", "herb"),
    "salvia": ("low", "herb"),
    "strelitzia": ("medium", "foliage"),
}


def genus(latin: str | None) -> str | None:
    if not latin:
        return None
    m = re.match(r"\s*([A-Za-z]+)", latin)
    return m.group(1).lower() if m else None


def catalog_defaults(latin: str | None) -> tuple[str, str] | None:
    return CATALOG.get(genus(latin) or "")


def fill_care_defaults(session: Session, user_id: int | None = None) -> int:
    """Fill empty water_need / feed_group from the catalog. Never overwrites a set value."""
    query = select(Plant)
    if user_id is not None:
        query = query.where(Plant.user_id == user_id)
    changed = 0
    for plant in session.scalars(query):
        defaults = catalog_defaults(plant.latin)
        if not defaults:
            continue
        if plant.water_need is None:
            plant.water_need = defaults[0]
            changed += 1
        if plant.feed_group is None:
            plant.feed_group = defaults[1]
            changed += 1
    session.commit()
    return changed


def fertilizers(session: Session, user_id: int) -> list[Product]:
    return list(
        session.scalars(
            select(Product).where(Product.user_id == user_id, Product.kind == "fertilizer").order_by(Product.id)
        )
    )
