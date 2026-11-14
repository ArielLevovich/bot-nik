import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram.ext import ConversationHandler

from botnik import sun, views
from botnik.db import make_engine, make_session_factory
from botnik.handlers import sun as sun_handlers
from botnik.seed import load_yaml, seed

USER = 111
AREAS = ["main_railing", "corner", "north_railing", "upper_opening", "back_wall", "ceiling_hanging", "entrance"]


@pytest.fixture()
def factory():
    f = make_session_factory(make_engine("sqlite://"))
    with f() as s:
        seed(s, load_yaml(), USER)
    return f


@pytest.mark.parametrize(
    "day, season",
    [(date(2026, 11, 14), "winter"), (date(2027, 1, 5), "winter"), (date(2027, 3, 31), "winter"),
     (date(2027, 4, 1), "summer"), (date(2027, 7, 1), "summer"), (date(2027, 9, 30), "summer"), (date(2027, 10, 1), "winter")],
)
def test_season_for(day, season):
    assert sun.season_for(day) == season


def test_areas_in_map_order(factory):
    with factory() as s:
        assert sun.areas(s, USER) == AREAS
        assert sun.unanswered(s, USER, "winter") == AREAS


def test_save_and_describe(factory):
    with factory() as s:
        sun.save(s, USER, "main_railing", "winter", morning_from=7, morning_to=12, afternoon_sun=False)
        sun.save(s, USER, "corner", "winter", morning_from=None, morning_to=None, afternoon_sun=True)
        assert sun.describe(sun.get(s, USER, "main_railing", "winter")) == "בוקר 07:00–12:00 · אחה״צ: אין"
        assert sun.describe(sun.get(s, USER, "corner", "winter")) == "אין שמש בבוקר · אחה״צ: יש"
        assert sun.describe(None) == "עוד לא נרשם"
        assert "main_railing" not in sun.unanswered(s, USER, "winter")
        assert "main_railing" in sun.unanswered(s, USER, "summer")  # seasons are separate


def test_save_again_updates_the_same_row(factory):
    with factory() as s:
        sun.save(s, USER, "corner", "winter", morning_from=8, morning_to=11, afternoon_sun=False)
        sun.save(s, USER, "corner", "winter", morning_from=9, morning_to=13, afternoon_sun=True)
        row = sun.get(s, USER, "corner", "winter")
        assert (row.morning_from, row.morning_to, row.afternoon_sun) == (9, 13, True)


def test_save_rejects_backwards_hours(factory):
    with factory() as s, pytest.raises(ValueError):
        sun.save(s, USER, "corner", "winter", morning_from=12, morning_to=9, afternoon_sun=False)


def test_card_and_missing_show_sun(factory):
    with factory() as s:
        text, _ = views.container_card(s, USER, 1)  # M4, main railing
        assert "שמש באזור" in text and "עוד לא נרשם" in text
        text, _ = views.missing_view(s, USER)
        assert "/sun" in text and "7 אזורים" in text
        sun.save(s, USER, "main_railing", "winter" if sun.season_for() == "winter" else "summer",
                 morning_from=7, morning_to=12, afternoon_sun=False)
        text, _ = views.container_card(s, USER, 1)
        assert "07:00–12:00" in text


def test_overview_buttons(factory):
    with factory() as s:
        text, kb = views.sun_overview(s, USER)
    callbacks = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert callbacks[0] == "sun:go"
    assert {f"sun:a:{a}" for a in AREAS} <= set(callbacks)
    assert text.count("❓") == 7


# --- conversation, driven with fake updates ---

class SunChat:
    def __init__(self, factory):
        self.factory = factory
        self.context = SimpleNamespace(application=SimpleNamespace(bot_data={"session_factory": factory}), user_data={})
        self.shown = []

    def _record(self, text, parse_mode=None, reply_markup=None):
        self.shown.append(text)

    def press(self, data):
        update = MagicMock()
        update.effective_user.id = USER
        update.callback_query.data = data
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock(side_effect=self._record)
        if data.startswith(("sun:go", "sun:a:")):
            handler = sun_handlers.start
        else:
            handler = {
                "sun:none": sun_handlers.on_no_morning, "sun:skip": sun_handlers.on_skip, "sun:cancel": sun_handlers.on_cancel,
            }.get(data) or (sun_handlers.on_afternoon if data.startswith("sun:pm:") else sun_handlers.on_hour)
        return asyncio.run(handler(update, self.context))


def test_walk_through_unanswered_areas(factory):
    chat = SunChat(factory)
    assert chat.press("sun:go") == sun_handlers.ASK
    assert "מעקה ראשי" in chat.shown[-1] and "מאיזו שעה" in chat.shown[-1]
    chat.press("sun:h:7")
    assert "עד איזו שעה" in chat.shown[-1]
    chat.press("sun:h:12")
    assert "אחרי הצהריים" in chat.shown[-1]
    chat.press("sun:pm:0")
    assert "פינה" in chat.shown[-1]  # next area
    chat.press("sun:none")
    chat.press("sun:pm:1")
    chat.press("sun:skip")  # north railing skipped
    assert "פתח עליון" in chat.shown[-1]
    assert chat.press("sun:cancel") == ConversationHandler.END
    assert chat.shown[-1].startswith("✅ נשמר.")
    season = sun.season_for()
    with factory() as s:
        assert sun.describe(sun.get(s, USER, "main_railing", season)) == "בוקר 07:00–12:00 · אחה״צ: אין"
        assert sun.describe(sun.get(s, USER, "corner", season)) == "אין שמש בבוקר · אחה״צ: יש"
        assert sun.unanswered(s, USER, season) == AREAS[2:]
    assert "sun" not in chat.context.user_data


def test_edit_one_area(factory):
    chat = SunChat(factory)
    chat.press("sun:a:entrance")
    assert "כניסה" in chat.shown[-1]
    chat.press("sun:h:9")
    chat.press("sun:h:11")
    assert chat.press("sun:pm:0") == ConversationHandler.END
    with factory() as s:
        assert sun.is_answered(sun.get(s, USER, "entrance", sun.season_for()))


def test_question_keyboards_fit(factory):
    for step, extra in [("from", {}), ("to", {"from": 14}), ("pm", {})]:
        text, kb = sun_handlers.question({"area": "corner", "season": "winter", "step": step, **extra})
        callbacks = [b.callback_data for row in kb.inline_keyboard for b in row]
        assert "sun:skip" in callbacks and "sun:cancel" in callbacks
        assert all(len(cb.encode()) <= 64 for cb in callbacks)
