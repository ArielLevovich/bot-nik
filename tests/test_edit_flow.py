"""Drive the real conversation handlers with fake Telegram updates (no network)."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram.ext import ConversationHandler

from botnik import editing
from botnik.db import make_engine, make_session_factory
from botnik.handlers import edit
from botnik.missing import missing_fields
from botnik.seed import load_yaml, seed

USER = 111


class Chat:
    """Collects what the bot shows; builds button presses and text messages."""

    def __init__(self):
        factory = make_session_factory(make_engine("sqlite://"))
        with factory() as s:
            seed(s, load_yaml(), USER)
        self.factory = factory
        self.context = SimpleNamespace(application=SimpleNamespace(bot_data={"session_factory": factory}), user_data={})
        self.shown: list[str] = []
        self.keyboard = None

    def _record(self, text, parse_mode=None, reply_markup=None):
        self.shown.append(text)
        self.keyboard = reply_markup

    def _update(self, data=None, text=None):
        message = MagicMock()
        message.text = text
        message.reply_text = AsyncMock(side_effect=self._record)
        update = MagicMock()
        update.effective_user.id = USER
        update.effective_message = message
        if data is None:
            update.callback_query = None
        else:
            update.callback_query.data = data
            update.callback_query.answer = AsyncMock()
            update.callback_query.edit_message_text = AsyncMock(side_effect=self._record)
        return update

    def press(self, data):
        return asyncio.run(self._handler_for(data)(self._update(data=data), self.context))

    def press_label(self, label):
        for row in self.keyboard.inline_keyboard:
            for b in row:
                if b.text == label:
                    return self.press(b.callback_data)
        raise AssertionError(f"no button {label!r}; have {[b.text for r in self.keyboard.inline_keyboard for b in r]}")

    def type(self, text):
        return asyncio.run(edit.on_text(self._update(text=text), self.context))

    @staticmethod
    def _handler_for(data):
        if data.startswith(("e:c:", "e:s:", "e:m:")):
            return edit.start
        return {editing.CB_SKIP: edit.on_skip, editing.CB_CANCEL: edit.on_cancel, editing.CB_OTHER: edit.on_other}.get(
            data, edit.on_choice
        )

    def container(self, n):
        with self.factory() as s:
            c = editing.find_container(s, USER, n)
            c.slot_code = c.slot.code if c.slot else None  # read while the session is open
            return c, missing_fields(c)


@pytest.fixture()
def chat():
    return Chat()


def test_complete_container_23_end_to_end(chat):
    assert chat.press("e:c:23") == edit.ASK
    assert "צורת המיכל" in chat.shown[-1]
    chat.press_label("עגול")
    assert "קוטר" in chat.shown[-1]
    assert chat.type("abc") == edit.ASK  # bad input: same question again, with a warning
    assert "⚠️" in chat.shown[-1] and "קוטר" in chat.shown[-1]
    chat.type("20 ס״מ")
    assert "גובה" in chat.shown[-1]
    chat.type("15")
    chat.press_label("✍️ משהו אחר")  # material: type it
    assert "כתוב במילים" in chat.shown[-1]
    chat.type("סל קש")
    chat.press_label("לבן")
    assert chat.type("פורח ויפה") == ConversationHandler.END
    assert chat.shown[-1].startswith("✅ נשמר.")
    c, missing = chat.container(23)
    assert missing == []
    assert (c.shape, c.outer_diameter_cm, c.outer_height_cm, c.material, c.color, c.condition) == (
        "round", 20, 15, "סל קש", "white", "פורח ויפה",
    )
    assert "edit" not in chat.context.user_data


def test_skip_and_cancel_keep_saved_answers(chat):
    chat.press("e:c:22")
    chat.press(editing.CB_SKIP)  # skip shape
    assert "ממה המיכל עשוי" in chat.shown[-1]
    chat.press_label("קרמיקה")
    assert chat.press(editing.CB_CANCEL) == ConversationHandler.END
    assert "הפסקתי" in chat.shown[-1]
    c, missing = chat.container(22)
    assert c.material == "ceramic" and "shape" in missing


def test_status_quick_action(chat):
    chat.press("e:s:2")
    chat.press_label("🔴 צריך טיפול")
    assert "לעדכן גם את התיאור" in chat.shown[-1]
    assert chat.press(editing.CB_SKIP) == ConversationHandler.END  # "leave as is"
    c, _ = chat.container(2)
    assert c.status == "needs_care" and c.condition == "די נפולות, הבסיס של כל רקפת נראה טוב"


def test_move_quick_action(chat):
    chat.press("e:m:1")
    chat.press_label("P1 · פינה")
    chat.press_label("רצפה")
    assert chat.shown[-1].startswith("✅ נשמר.")
    c, _ = chat.container(1)
    assert c.slot_code == "P1" and c.level == "floor"


def test_typing_on_a_button_question_asks_to_use_buttons(chat):
    chat.press("e:m:1")
    assert chat.type("M2") == edit.ASK
    assert "בכפתורים" in chat.shown[-1]
