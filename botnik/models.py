"""SQLAlchemy models: slot -> container -> plant, plus product.

Every table that belongs to a user has `user_id` so more users can be added later.
`None` in a field means "not provided yet".
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import JSON, BigInteger, Date, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

STATUSES = ("good", "watch", "needs_care", "unknown")
LEVELS = ("railing", "railing_hanging", "shelf", "floor", "hanging")
PEST_PROFILES = ("normal", "sensitive")


class Base(DeclarativeBase):
    pass


class Slot(Base):
    """A fixed location on the balcony map (M1..M5, P1, N1..N3, ...)."""

    __tablename__ = "slot"
    __table_args__ = (UniqueConstraint("user_id", "code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    code: Mapped[str] = mapped_column(String(8))
    area: Mapped[str] = mapped_column(String(32))
    note: Mapped[str | None] = mapped_column(Text)
    free: Mapped[bool] = mapped_column(default=False)

    containers: Mapped[list[Container]] = relationship(
        back_populates="slot", foreign_keys="Container.slot_id", order_by="Container.number"
    )


class Container(Base):
    """A pot or planter. It can move between slots."""

    __tablename__ = "container"
    __table_args__ = (UniqueConstraint("user_id", "number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    number: Mapped[int] = mapped_column(Integer)  # the owner-facing number (id in garden.yaml)

    slot_id: Mapped[int | None] = mapped_column(ForeignKey("slot.id"))
    between_slot_id: Mapped[int | None] = mapped_column(ForeignKey("slot.id"))
    level: Mapped[str | None] = mapped_column(String(32))
    type_code: Mapped[str | None] = mapped_column(String(32))  # e.g. red_rail_large

    shape: Mapped[str | None] = mapped_column(String(32))  # round / rectangular / elliptical / roundish
    material: Mapped[str | None] = mapped_column(String(64))
    color: Mapped[str | None] = mapped_column(String(32))
    # Outer dimensions in cm, measured with the plant inside.
    outer_length_cm: Mapped[float | None] = mapped_column(Float)
    outer_width_cm: Mapped[float | None] = mapped_column(Float)
    outer_height_cm: Mapped[float | None] = mapped_column(Float)
    outer_diameter_cm: Mapped[float | None] = mapped_column(Float)
    outer_raw: Mapped[str | None] = mapped_column(String(64))  # unparsed measurement, e.g. "10 × 12"
    substrate: Mapped[str | None] = mapped_column(String(64))
    sections: Mapped[list | None] = mapped_column(JSON)  # e.g. ["A", "B"]

    stand_height_cm: Mapped[float | None] = mapped_column(Float)
    hang_height_cm: Mapped[float | None] = mapped_column(Float)
    position_note: Mapped[str | None] = mapped_column(Text)
    sun_note: Mapped[str | None] = mapped_column(Text)
    hang_note: Mapped[str | None] = mapped_column(Text)

    status: Mapped[str] = mapped_column(String(16), default="unknown")
    condition: Mapped[str | None] = mapped_column(Text)
    missing: Mapped[list] = mapped_column(JSON, default=list)

    slot: Mapped[Slot | None] = relationship(back_populates="containers", foreign_keys=[slot_id])
    between_slot: Mapped[Slot | None] = relationship(foreign_keys=[between_slot_id])
    plants: Mapped[list[Plant]] = relationship(
        back_populates="container", order_by="Plant.position", cascade="all, delete-orphan"
    )


class Plant(Base):
    __tablename__ = "plant"
    __table_args__ = (UniqueConstraint("container_id", "position"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    container_id: Mapped[int] = mapped_column(ForeignKey("container.id"))
    position: Mapped[int] = mapped_column(Integer)  # order inside the container
    section: Mapped[str | None] = mapped_column(String(4))

    name_he: Mapped[str] = mapped_column(String(128))
    name_en: Mapped[str | None] = mapped_column(String(128))
    latin: Mapped[str | None] = mapped_column(String(128))
    latin_verified: Mapped[bool] = mapped_column(default=False)
    note: Mapped[str | None] = mapped_column(Text)

    status: Mapped[str] = mapped_column(String(16), default="unknown")
    condition: Mapped[str | None] = mapped_column(Text)
    pest_profile: Mapped[str] = mapped_column(String(16), default="normal")
    pests_history: Mapped[list] = mapped_column(JSON, default=list)
    planted_on: Mapped[date | None] = mapped_column(Date)

    container: Mapped[Container] = relationship(back_populates="plants")


class Product(Base):
    """Fertilizers and pest treatments the owner has at home."""

    __tablename__ = "product"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    name: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(32))  # fertilizer / pest_treatment
    npk: Mapped[str | None] = mapped_column(String(32))
    rules: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
