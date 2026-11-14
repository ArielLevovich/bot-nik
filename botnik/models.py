"""SQLAlchemy models: slot -> container -> plant, plus product.

Every table that belongs to a user has `user_id` so more users can be added later.
`None` in a field means "not provided yet".
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, BigInteger, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
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
    # Learned from the owner's taps: + days when "not needed", - days when "looks dry" (limited in rules.py).
    water_adjust_days: Mapped[float | None] = mapped_column(Float)
    # Only items that can't be computed from the fields; see botnik.missing.missing_fields().
    # (Column keeps its original name "missing" so existing databases still open.)
    missing_extra: Mapped[list] = mapped_column("missing", JSON, default=list)

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
    water_need: Mapped[str | None] = mapped_column(String(8))  # low / medium / high
    feed_group: Mapped[str | None] = mapped_column(String(16))  # flowering / edible / herb / succulent / foliage
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


class AreaSun(Base):
    """Sun hours for one balcony area in one season, as reported by the owner.

    None = not answered yet. morning_sun False means "no morning sun" (then from/to stay None).
    """

    __tablename__ = "area_sun"
    __table_args__ = (UniqueConstraint("user_id", "area", "season"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    area: Mapped[str] = mapped_column(String(32))
    season: Mapped[str] = mapped_column(String(8))  # winter / summer
    morning_sun: Mapped[bool | None] = mapped_column()
    morning_from: Mapped[int | None] = mapped_column(Integer)  # hour, 5..15
    morning_to: Mapped[int | None] = mapped_column(Integer)
    afternoon_sun: Mapped[bool | None] = mapped_column()


class CareEvent(Base):
    """Something done to a container: water, feed, move, note. Times are naive UTC."""

    __tablename__ = "care_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    container_id: Mapped[int] = mapped_column(ForeignKey("container.id"), index=True)
    plant_id: Mapped[int | None] = mapped_column(ForeignKey("plant.id"))
    type: Mapped[str] = mapped_column(String(16))  # water / feed / move / note
    amount_l: Mapped[float | None] = mapped_column(Float)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("product.id"))
    at: Mapped[datetime] = mapped_column(DateTime)
    source: Mapped[str] = mapped_column(String(16))  # button / command / task / baseline
    note: Mapped[str | None] = mapped_column(Text)
    batch: Mapped[str] = mapped_column(String(16), index=True)  # events saved together, undone together


class Task(Base):
    """A reminder in the morning brief: water or feed one container."""

    __tablename__ = "task"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    container_id: Mapped[int] = mapped_column(ForeignKey("container.id"), index=True)
    type: Mapped[str] = mapped_column(String(8))  # water / feed
    due_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="open")  # open / postponed / done / not_needed
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)  # also the time of the last postpone
    care_event_id: Mapped[int | None] = mapped_column(ForeignKey("care_event.id"))

    container: Mapped[Container] = relationship()


class UserSettings(Base):
    __tablename__ = "user_settings"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    brief_time: Mapped[str] = mapped_column(String(5), default="05:50")
    evening_time: Mapped[str] = mapped_column(String(5), default="19:30")
    timezone: Mapped[str] = mapped_column(String(32), default="Asia/Jerusalem")
