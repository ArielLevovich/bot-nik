"""Configuration loaded from .env (python-dotenv)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def parse_user_ids(raw: str | None) -> frozenset[int]:
    """Parse a comma-separated list of Telegram user IDs. Empty -> empty set."""
    if not raw:
        return frozenset()
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError as exc:
            raise ConfigError(f"ALLOWED_USER_IDS contains a non-numeric value: {part!r}") from exc
    return frozenset(ids)


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    allowed_user_ids: frozenset[int]


def load_settings(env_file: Path | None = None) -> Settings:
    """Read settings from the environment, loading .env from the project root first."""
    load_dotenv(env_file or PROJECT_ROOT / ".env")
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise ConfigError("TELEGRAM_BOT_TOKEN is missing. Copy .env.example to .env and fill it in.")
    return Settings(
        telegram_bot_token=token,
        allowed_user_ids=parse_user_ids(os.getenv("ALLOWED_USER_IDS")),
    )
