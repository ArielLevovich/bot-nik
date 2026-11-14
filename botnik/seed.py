"""Load data/garden.yaml into the database.

Usage: python -m botnik.seed

Idempotent: rows are matched by (user_id, slot code), (user_id, container number),
(container, plant position) and (user_id, product name), then inserted or updated.
Running it twice gives the same database.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.orm import Session

from botnik.config import PROJECT_ROOT, parse_user_ids
from botnik.db import make_engine, make_session_factory
from botnik.models import Container, Plant, Product, Slot

GARDEN_YAML = PROJECT_ROOT / "data" / "garden.yaml"


def load_yaml(path: Path = GARDEN_YAML) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _expand_type(raw: dict[str, Any], types: dict[str, Any]) -> dict[str, Any]:
    """Merge a container with its container_type (container fields win)."""
    type_code = raw.get("type")
    if not type_code:
        return dict(raw)
    if type_code not in types:
        raise ValueError(f"Container {raw.get('id')}: unknown type {type_code!r}")
    merged = {k: v for k, v in types[type_code].items() if k not in ("description", "plants_per_section")}
    merged["outer"] = {**(merged.get("outer") or {}), **(raw.get("outer") or {})}
    merged.update({k: v for k, v in raw.items() if k != "outer"})
    return merged


def _upsert(session: Session, model, lookup: dict[str, Any], values: dict[str, Any]):
    row = session.scalars(select(model).filter_by(**lookup)).one_or_none()
    if row is None:
        row = model(**lookup)
        session.add(row)
    for key, value in values.items():
        setattr(row, key, value)
    return row


def seed(session: Session, data: dict[str, Any], user_id: int) -> dict[str, int]:
    slots: dict[str, Slot] = {}
    for s in data.get("slots") or []:
        slots[s["code"]] = _upsert(
            session,
            Slot,
            {"user_id": user_id, "code": s["code"]},
            {"area": s["area"], "note": s.get("note"), "free": bool(s.get("free", False))},
        )
    session.flush()

    types = data.get("container_types") or {}
    n_plants = 0
    for raw in data.get("containers") or []:
        c = _expand_type(raw, types)
        outer = c.get("outer") or {}
        slot_code, between_code = c.get("slot"), c.get("between")
        for code in (slot_code, between_code):
            if code is not None and code not in slots:
                raise ValueError(f"Container {c['id']}: unknown slot {code!r}")
        container = _upsert(
            session,
            Container,
            {"user_id": user_id, "number": c["id"]},
            {
                "slot_id": slots[slot_code].id if slot_code else None,
                "between_slot_id": slots[between_code].id if between_code else None,
                "level": c.get("level"),
                "type_code": c.get("type"),
                "shape": c.get("shape"),
                "material": c.get("material"),
                "color": c.get("color"),
                "outer_length_cm": outer.get("length"),
                "outer_width_cm": outer.get("width"),
                "outer_height_cm": outer.get("height"),
                "outer_diameter_cm": outer.get("diameter"),
                "outer_raw": c.get("outer_raw"),
                "substrate": c.get("substrate"),
                "sections": c.get("sections"),
                "stand_height_cm": c.get("stand_height_cm"),
                "hang_height_cm": c.get("hang_height_cm"),
                "position_note": c.get("position_note"),
                "sun_note": c.get("sun_note"),
                "hang_note": c.get("hang_note"),
                "status": c.get("status") or "unknown",
                "condition": c.get("condition"),
                "missing": [str(m) for m in c.get("missing") or []],
            },
        )
        session.flush()

        raw_plants = c.get("plants") or []
        for position, p in enumerate(raw_plants):
            _upsert(
                session,
                Plant,
                {"container_id": container.id, "position": position},
                {
                    "user_id": user_id,
                    "section": p.get("section"),
                    "name_he": p["name_he"],
                    "name_en": p.get("name_en"),
                    "latin": p.get("latin"),
                    "latin_verified": bool(p.get("latin_verified", False)),
                    "note": p.get("note"),
                    # In the YAML these are recorded per container; each plant starts with them.
                    "status": c.get("status") or "unknown",
                    "condition": c.get("condition"),
                    "pest_profile": c.get("pest_profile") or "normal",
                    "pests_history": list(c.get("pests_history") or []),
                    "planted_on": c.get("planted"),
                },
            )
            n_plants += 1
        # Plants removed from the YAML are removed from the container too.
        for extra in session.scalars(
            select(Plant).where(Plant.container_id == container.id, Plant.position >= len(raw_plants))
        ):
            session.delete(extra)

    for p in data.get("products") or []:
        _upsert(
            session,
            Product,
            {"user_id": user_id, "name": p["name"]},
            {"kind": p["kind"], "npk": p.get("npk"), "rules": p.get("rules"), "note": p.get("note")},
        )

    session.commit()
    return {
        "slots": len(slots),
        "containers": len(data.get("containers") or []),
        "plants": n_plants,
        "products": len(data.get("products") or []),
    }


def owner_user_id() -> int:
    """The single owner for now: the first ID in ALLOWED_USER_IDS."""
    load_dotenv(PROJECT_ROOT / ".env")
    ids = parse_user_ids(os.getenv("ALLOWED_USER_IDS"))
    if not ids:
        sys.exit("ALLOWED_USER_IDS is empty in .env. Send /myid to the bot and add your ID first.")
    return min(ids)


def main() -> None:
    user_id = owner_user_id()
    engine = make_engine()
    with make_session_factory(engine)() as session:
        counts = seed(session, load_yaml(), user_id)
    print(
        f"Loaded {counts['slots']} slots, {counts['containers']} containers, "
        f"{counts['plants']} plants, {counts['products']} products into {engine.url.database}"
    )


if __name__ == "__main__":
    main()
