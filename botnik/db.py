"""Database engine and sessions (SQLite file botnik.db in the project root)."""

from __future__ import annotations

import logging

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from botnik.config import db_path
from botnik.models import Base

log = logging.getLogger(__name__)


def add_missing_columns(engine: Engine) -> list[str]:
    """Tiny migration: add new nullable model columns to existing tables (data is kept).

    create_all() makes new tables but never changes existing ones. Only nullable
    columns are added automatically; anything else needs a real migration.
    """
    added = []
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            existing = {c["name"] for c in insp.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing:
                    continue
                if not column.nullable or column.primary_key:
                    raise RuntimeError(f"Cannot add required column {table.name}.{column.name} automatically")
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {column.type.compile(engine.dialect)}'))
                added.append(f"{table.name}.{column.name}")
    for name in added:
        log.info("Added column %s", name)
    return added


def default_db_url() -> str:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path}"


def make_engine(url: str | None = None) -> Engine:
    engine = create_engine(url or default_db_url())
    Base.metadata.create_all(engine)
    add_missing_columns(engine)
    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
