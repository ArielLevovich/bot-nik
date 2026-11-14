"""The real Application is wired so the allow-list gate runs before every handler except /myid."""

from telegram.ext import CallbackQueryHandler, CommandHandler, TypeHandler

from botnik.bot import build_application
from botnik.config import Settings
from botnik.db import make_engine, make_session_factory
from botnik.handlers.auth import GATE_GROUP, PRE_GATE_GROUP


def _app():
    settings = Settings(telegram_bot_token="123:TEST", allowed_user_ids=frozenset({111}))
    return build_application(settings, make_session_factory(make_engine("sqlite://")))


def _commands(handlers):
    return {cmd for h in handlers if isinstance(h, CommandHandler) for cmd in h.commands}


def test_only_myid_runs_before_the_gate():
    groups = _app().handlers
    assert min(groups) == PRE_GATE_GROUP
    assert _commands(groups[PRE_GATE_GROUP]) == {"myid"}
    assert len(groups[GATE_GROUP]) == 1 and isinstance(groups[GATE_GROUP][0], TypeHandler)


def test_all_other_handlers_are_behind_the_gate():
    groups = _app().handlers
    behind = [h for g, hs in groups.items() if g > GATE_GROUP for h in hs]
    assert _commands(behind) == {"start", "garden", "missing", "sun", "cancel", "today", "water", "feed", "care", "settings", "backup", "restore"}
    assert any(isinstance(h, CallbackQueryHandler) for h in behind)
