"""Plant photos on the server: EXIF (including GPS location) removed, resized, linked to a pot and issue."""

from __future__ import annotations

import io
import re
import secrets
from pathlib import Path

from PIL import Image, ImageOps
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from botnik import clock
from botnik.models import Container, Photo

MAX_SIDE = 1600
JPEG_QUALITY = 85
_CAPTION_NUMBER = re.compile(r"#\s*(\d+)")


def photos_dir(engine: Engine) -> Path:
    path = Path(engine.url.database).parent / "photos"
    path.mkdir(parents=True, exist_ok=True)
    return path


def clean_image(data: bytes) -> bytes:
    """Re-encode as JPEG: orientation applied, at most MAX_SIDE px, and no metadata at all."""
    with Image.open(io.BytesIO(data)) as img:
        img = ImageOps.exif_transpose(img)  # keep it upright before the EXIF is dropped
        img = img.convert("RGB")
        img.thumbnail((MAX_SIDE, MAX_SIDE))
        out = io.BytesIO()
        img.save(out, "JPEG", quality=JPEG_QUALITY)  # no exif= -> nothing carried over
    return out.getvalue()


def container_from_caption(caption: str | None) -> int | None:
    m = _CAPTION_NUMBER.search(caption or "")
    return int(m.group(1)) if m else None


def add(
    session: Session, engine: Engine, container: Container, data: bytes, *,
    plant_id: int | None = None, issue_id: int | None = None,
) -> Photo:
    now = clock.now_utc()
    relative = Path(str(container.number)) / f"{clock.local_date(now):%Y-%m-%d}-{secrets.token_hex(3)}.jpg"
    target = photos_dir(engine) / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(clean_image(data))
    photo = Photo(
        user_id=container.user_id, container_id=container.id, plant_id=plant_id, issue_id=issue_id,
        path=str(relative), taken_at=now,
    )
    session.add(photo)
    session.commit()
    return photo


def latest(session: Session, container_id: int, n: int = 2) -> list[Photo]:
    return list(
        session.scalars(
            select(Photo).where(Photo.container_id == container_id).order_by(Photo.taken_at.desc(), Photo.id.desc()).limit(n)
        )
    )


def count(session: Session, container_id: int) -> int:
    return len(list(session.scalars(select(Photo.id).where(Photo.container_id == container_id))))


def file_for(engine: Engine, photo: Photo) -> Path:
    return photos_dir(engine) / photo.path
