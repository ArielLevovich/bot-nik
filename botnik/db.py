"""Database engine and sessions (SQLite file botnik.db in the project root)."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from botnik.config import PROJECT_ROOT
from botnik.models import Base

DEFAULT_DB_URL = f"sqlite:///{PROJECT_ROOT / 'botnik.db'}"


def make_engine(url: str = DEFAULT_DB_URL) -> Engine:
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
