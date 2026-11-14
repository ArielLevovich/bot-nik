import asyncio
import shutil
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import func, select, text

from botnik import backup
from botnik.db import make_engine, make_session_factory
from botnik.editing import apply_answer, find_container
from botnik.handlers import admin, basic
from botnik.models import Container
from botnik.seed import load_yaml, seed

USER = 111


@pytest.fixture()
def live(tmp_path):
    """A file-based database like the real one (backups need a file)."""
    (tmp_path / "live").mkdir()
    engine = make_engine(f"sqlite:///{tmp_path / 'live' / 'botnik.db'}")
    factory = make_session_factory(engine)
    with factory() as s:
        seed(s, load_yaml(), USER)
    return engine, factory


def count(factory):
    with factory() as s:
        return s.scalar(select(func.count()).select_from(Container))


def test_db_path_from_environment(monkeypatch, tmp_path):
    from botnik.config import db_path

    monkeypatch.setenv("BOTNIK_DB_PATH", str(tmp_path / "data" / "botnik.db"))
    assert db_path() == tmp_path / "data" / "botnik.db"


def test_snapshot_and_check(live, tmp_path):
    engine, _ = live
    copy = backup.snapshot(engine, tmp_path / "copy.db")
    assert backup.check(copy) == (True, "24 עציצים, 29 צמחים")


def test_check_rejects_wrong_files(tmp_path):
    (tmp_path / "photo.jpg").write_bytes(b"\xff\xd8\xff not a db")
    assert backup.check(tmp_path / "photo.jpg")[0] is False
    other = make_engine(f"sqlite:///{tmp_path / 'other.db'}")
    with other.begin() as conn:
        conn.execute(text("DROP TABLE container"))
    assert backup.check(tmp_path / "other.db")[0] is False
    empty = tmp_path / "empty.db"
    make_engine(f"sqlite:///{empty}")
    assert backup.check(empty) == (False, "הקובץ ריק – אין בו עציצים.")


def test_daily_backup_keeps_14(live):
    engine, _ = live
    start = date(2026, 11, 1)
    for i in range(20):
        backup.daily_backup(engine, start + timedelta(days=i))
    files = sorted(p.name for p in backup.backups_dir(engine).glob("botnik-*.db"))
    assert len(files) == 14 and files[0] == "botnik-2026-11-07.db" and files[-1] == "botnik-2026-11-20.db"


def test_restore_replaces_data_and_keeps_safety_copy(live, tmp_path):
    engine, factory = live
    good = backup.snapshot(engine, tmp_path / "good.db")  # 24 containers
    with factory() as s:
        apply_answer(s, find_container(s, USER, 1), "condition", "changed after the backup")
    safety = backup.restore(engine, good)
    with factory() as s:
        assert find_container(s, USER, 1).condition == "בפריחה"
    assert backup.check(safety)[0] and safety.name.startswith("botnik-before-restore-")


def test_restore_older_file_gets_new_columns(live, tmp_path):
    engine, factory = live
    old = backup.snapshot(engine, tmp_path / "old.db")
    old_engine = make_engine(f"sqlite:///{old}")
    with old_engine.begin() as conn:  # make it look like a Task-02 database
        conn.execute(text("DROP TABLE care_event"))
        conn.execute(text("ALTER TABLE plant DROP COLUMN water_need"))
    old_engine.dispose()
    backup.restore(engine, old)
    with factory() as s:
        assert count(factory) == 24
        assert s.execute(text("SELECT count(*) FROM care_event")).scalar() == 0
        assert "water_need" in [r[1] for r in s.execute(text("PRAGMA table_info(plant)"))]


# --- Telegram side ---

class Chat:
    def __init__(self, factory):
        self.context = SimpleNamespace(
            application=SimpleNamespace(bot_data={"session_factory": factory}), user_data={}, bot=MagicMock()
        )
        self.replies, self.documents = [], []

    def update(self, document_path: Path | None = None):
        u = MagicMock()
        u.effective_user.id = USER
        u.effective_message.reply_text = AsyncMock(side_effect=lambda t, **k: self.replies.append(t))

        async def reply_document(f, filename, caption):
            self.documents.append((filename, f.read()))

        u.effective_message.reply_document = AsyncMock(side_effect=reply_document)
        if document_path:
            u.effective_message.document.file_id = "f1"
            tg_file = MagicMock()
            tg_file.download_to_drive = AsyncMock(side_effect=lambda dest: shutil.copy(document_path, dest))
            self.context.bot.get_file = AsyncMock(return_value=tg_file)
        return u

    def run(self, handler, document_path=None):
        asyncio.run(handler(self.update(document_path), self.context))


def test_backup_command_sends_the_database(live):
    _, factory = live
    chat = Chat(factory)
    chat.run(admin.backup_cmd)
    name, data = chat.documents[-1]
    assert name.startswith("botnik-") and data.startswith(backup.SQLITE_HEADER)


def test_restore_flow(live, tmp_path):
    engine, factory = live
    good = backup.snapshot(engine, tmp_path / "good.db")
    chat = Chat(factory)
    chat.run(admin.on_document, good)  # not asked for: ignored
    assert "לא ביקשת שחזור" in chat.replies[-1]
    chat.run(admin.restore_cmd)
    (tmp_path / "bad.db").write_bytes(b"nope")
    chat.run(admin.on_document, tmp_path / "bad.db")
    assert chat.replies[-1].startswith("⚠️") and chat.context.user_data.get(admin.AWAITING)
    chat.run(admin.on_document, good)
    assert chat.replies[-1].startswith("✅ שוחזר: 24 עציצים")
    assert admin.AWAITING not in chat.context.user_data


def test_cancel_stops_a_pending_restore(live):
    _, factory = live
    chat = Chat(factory)
    chat.run(admin.restore_cmd)
    chat.run(basic.cancel_idle)
    assert "השחזור בוטל" in chat.replies[-1] and admin.AWAITING not in chat.context.user_data


def test_backup_job(live):
    engine, factory = live
    chat = Chat(factory)
    asyncio.run(admin.backup_job(chat.context))
    assert list(backup.backups_dir(engine).glob("botnik-????-??-??.db"))
