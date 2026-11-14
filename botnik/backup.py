"""Backups and restore of the SQLite database (safe while the bot is running).

Uses SQLite's own backup API, so a copy taken mid-write is still consistent.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import Engine

from botnik.db import add_missing_columns
from botnik.models import Base

KEEP_DAILY = 14
SQLITE_HEADER = b"SQLite format 3\x00"


def db_file(engine: Engine) -> Path:
    return Path(engine.url.database)


def backups_dir(engine: Engine) -> Path:
    path = db_file(engine).parent / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def copy_db(src: Path, dest: Path) -> None:
    source, target = sqlite3.connect(src), sqlite3.connect(dest)
    try:
        source.backup(target)
    finally:
        source.close()
        target.close()


def snapshot(engine: Engine, dest: Path) -> Path:
    copy_db(db_file(engine), dest)
    return dest


def daily_backup(engine: Engine, today: date, keep: int = KEEP_DAILY) -> Path:
    folder = backups_dir(engine)
    dest = snapshot(engine, folder / f"botnik-{today:%Y-%m-%d}.db")
    dailies = sorted(folder.glob("botnik-????-??-??.db"))
    for old in dailies[:-keep]:
        old.unlink()
    return dest


def check(path: Path) -> tuple[bool, str]:
    """Is this a Bot-Nik database? Returns (ok, Hebrew explanation or summary)."""
    try:
        with open(path, "rb") as f:
            if f.read(16) != SQLITE_HEADER:
                return False, "זה לא קובץ מסד נתונים (צריך את botnik.db)."
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"container", "plant", "slot"} <= tables:
                return False, "זה מסד נתונים, אבל לא של בוט־ניק."
            containers = conn.execute("SELECT count(*) FROM container").fetchone()[0]
            plants = conn.execute("SELECT count(*) FROM plant").fetchone()[0]
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        return False, "הקובץ פגום או לא נקרא."
    if containers == 0:
        return False, "הקובץ ריק – אין בו עציצים."
    return True, f"{containers} עציצים, {plants} צמחים"


def restore(engine: Engine, src: Path) -> Path:
    """Replace the live database with `src`. Saves the current one first; returns that safety copy."""
    safety = snapshot(engine, backups_dir(engine) / f"botnik-before-restore-{datetime.now():%Y%m%d-%H%M%S}.db")
    engine.dispose()  # close pooled connections; the next session opens the restored data
    copy_db(src, db_file(engine))
    Base.metadata.create_all(engine)  # an older file gets today's tables ...
    add_missing_columns(engine)  # ... and columns
    return safety
