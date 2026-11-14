# Task 01 – Phase 0 + start of Phase 1

Goal: a bot that runs on the owner's computer, answers only him, and can show the whole garden from `data/garden.yaml`.

## Steps
1. Project skeleton
   - `pyproject.toml` (or `requirements.txt`), `.gitignore`, `.env.example`, `README.md` (Hebrew, short: how to install and run).
   - Package layout: `botnik/` with `config.py`, `db.py`, `models.py`, `seed.py`, `bot.py`, `handlers/`.
   - `git init` and a first commit.
2. Config + allow-list
   - Load `TELEGRAM_BOT_TOKEN` and `ALLOWED_USER_IDS` from `.env`.
   - One filter so non-allowed users get no response.
3. Database
   - SQLAlchemy models: `slot`, `container`, `plant`, `product` (see CLAUDE.md). Include `missing` as JSON on container.
   - `python -m botnik.seed` loads `data/garden.yaml` into `botnik.db`. Running it twice must not duplicate rows (upsert by id/code).
   - Helper that estimates inner volume (L) and soil surface (cm²) from outer dimensions + shape; returns None when a dimension is missing. Unit tests for round, rectangular, elliptical, roundish.
4. Telegram commands (Hebrew text, inline buttons)
   - `/start` – short greeting and what the bot can do.
   - `/myid` – replies with the user's Telegram ID (works before the allow-list is filled; this is the only exception).
   - `/garden` – list of areas → slots → containers with plant names and a status emoji (🟢 good, 🟡 watch, 🔴 needs_care, ⚪ unknown).
   - Container card: all fields, estimated volume, plants, condition, and what is missing.
   - `/missing` – every container with missing fields, so the owner can complete them.
5. Tests: `pytest` passes (seed idempotency, volume helper, allow-list).

## Done when
- The owner sends `/garden` and sees all 24 containers in the right places.
- `/missing` lists containers 2, 3, 4, 7, 21–24.
- Tests pass.

Not in this task: watering reminders, scheduling, weather, photos, LLM.
