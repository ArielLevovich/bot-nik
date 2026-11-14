"""Reminder and care-log screens driven with fake Telegram updates (no network)."""

import asyncio
from datetime import timedelta
from html.parser import HTMLParser
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from botnik import brief, carelog, clock, tasks
from botnik.bot import build_application
from botnik.config import Settings
from botnik.db import make_engine, make_session_factory
from botnik.editing import find_container
from botnik.handlers import care, daily
from botnik.models import CareEvent, Task
from botnik.seed import load_yaml, seed

USER = 111
TODAY = clock.today()


class Html(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []

    def handle_starttag(self, tag, attrs):
        assert tag in ("b", "i"), tag
        self.stack.append(tag)

    def handle_endtag(self, tag):
        assert self.stack.pop() == tag


def valid(text):
    h = Html()
    h.feed(text)
    assert not h.stack and len(text) < 4096
    return text


class Chat:
    def __init__(self):
        self.factory = make_session_factory(make_engine("sqlite://"))
        with self.factory() as s:
            seed(s, load_yaml(), USER)
        self.app = SimpleNamespace(bot_data={"session_factory": self.factory})
        self.context = SimpleNamespace(application=self.app, user_data={})
        self.shown, self.keyboard, self.toasts = [], None, []

    def _record(self, text, parse_mode=None, reply_markup=None):
        self.shown.append(valid(text))
        self.keyboard = reply_markup

    def _update(self, data=None):
        u = MagicMock()
        u.effective_user.id = USER
        u.effective_message.reply_text = AsyncMock(side_effect=self._record)
        if data is None:
            u.callback_query = None
        else:
            u.callback_query.data = data
            u.callback_query.answer = AsyncMock(side_effect=lambda *a, **k: self.toasts.append(a[0] if a else ""))
            u.callback_query.edit_message_text = AsyncMock(side_effect=self._record)
        return u

    def command(self, handler):
        asyncio.run(handler(self._update(), self.context))

    def press(self, handler, data):
        asyncio.run(handler(self._update(data), self.context))

    def callbacks(self):
        return [b.callback_data for row in self.keyboard.inline_keyboard for b in row] if self.keyboard else []

    def session(self):
        return self.factory()


@pytest.fixture()
def chat():
    return Chat()


def test_card_water_button_and_undo(chat):
    chat.press(care.card_button, "c:w:9")
    assert chat.shown[-1].startswith("✅ נרשמה השקיה ל־#9")
    assert "אחרונה היום" in chat.shown[-1]
    undo = next(cb for cb in chat.callbacks() if cb.startswith("c:u:"))
    chat.press(care.card_button, undo)
    assert chat.shown[-1].startswith("↩️ בוטל")
    with chat.session() as s:
        assert s.scalars(select(CareEvent)).all() == []


def test_card_feed_button_uses_the_only_fertilizer(chat):
    chat.press(care.card_button, "c:f:1")
    assert "נרשם דישון ל־#1 (מדשן אצות)" in chat.shown[-1]


def test_water_command_asks_baseline_first_then_menu(chat):
    chat.command(care.water_cmd)
    assert "נקודת התחלה" in chat.shown[-1] and "מעקה ראשי" in chat.shown[-1]
    for _ in range(20):  # answer every question: water "yesterday", feed "2-3 weeks"
        cbs = [cb for cb in chat.callbacks() if cb.startswith("b:")]
        if not cbs:
            break
        pick = next(cb for cb in cbs if cb.endswith(":1") or cb.endswith(":17") or cb == "b:skip")
        chat.press(care.baseline_button, pick)
    assert "נקודת ההתחלה נשמרה" in chat.shown[-1]
    with chat.session() as s:
        assert carelog.areas_without_history(s, USER, "water") == []
        assert carelog.last_date(s, find_container(s, USER, 9).id, "water") == TODAY - timedelta(days=1)
    chat.command(care.water_cmd)  # asked only once
    assert "מה השקית" in chat.shown[-1]


def test_baseline_dont_remember_is_remembered(chat):
    chat.command(care.water_cmd)
    area_cb = next(cb for cb in chat.callbacks() if cb.endswith(":x"))
    chat.press(care.baseline_button, area_cb)
    assert "מעקה ראשי" not in chat.shown[-1]  # moved on to the next area


def test_water_whole_area_and_undo(chat):
    chat.press(care.water_button, "w:w:a:north_railing")  # N1: #5 #19, N2: #4, N3: #2
    assert chat.shown[-1] == "✅ נרשם השקיה ל־4 עציצים: #5, #19, #4, #2"
    with chat.session() as s:
        n = len(s.scalars(select(CareEvent)).all())
    chat.press(care.card_button, next(cb for cb in chat.callbacks() if cb.startswith("c:u:")))
    with chat.session() as s:
        assert n == 4 and s.scalars(select(CareEvent)).all() == []


def test_water_one_pot_via_pick(chat):
    chat.press(care.water_button, "w:w:pick")
    assert "w:w:c:12" in chat.callbacks()
    chat.press(care.water_button, "w:w:c:12")
    assert chat.shown[-1] == "✅ נרשם השקיה ל־#12"


def test_feed_command(chat):
    with chat.session() as s:  # pretend the baseline was answered
        for c in tasks.containers_in_map_order(s, USER):
            carelog.log(s, c, "water", source="baseline", commit=False)
            carelog.log(s, c, "feed", source="baseline", commit=False)
        s.commit()
    chat.command(care.feed_cmd)
    assert "מה דישנת" in chat.shown[-1]
    kind_cb = chat.callbacks()[0]
    assert kind_cb.startswith("w:f") and kind_cb.endswith(":all")


def test_morning_brief_buttons(chat):
    chat.command(daily.today_cmd)
    text = chat.shown[-1]
    assert text.startswith("☀️ <b>בוקר טוב</b>") and "#9" in text
    assert "t:all:m" in chat.callbacks()
    done_cb = next(cb for cb in chat.callbacks() if cb.startswith("t:d:"))
    chat.press(daily.task_button, done_cb)
    assert chat.toasts[-1] == "✓ נרשם" and "✅" in chat.shown[-1]
    chat.press(daily.task_button, done_cb)  # pressed twice
    assert chat.toasts[-1] == "המשימה כבר טופלה."
    skip_cb = next(cb for cb in chat.callbacks() if cb.startswith("t:n:"))
    chat.press(daily.task_button, skip_cb)
    assert "✖️" in chat.shown[-1]
    chat.press(daily.task_button, "t:all:m")
    assert "הכל בוצע להיום" in chat.shown[-1]
    assert not any(cb.startswith("t:d:") for cb in chat.callbacks())


def test_evening_summary_and_dry_report(chat):
    with chat.session() as s:
        tasks.generate(s, USER, TODAY)
        text, kb = brief.evening(s, USER, TODAY)
    assert valid(text).startswith("🌙 <b>סיכום ערב</b>") and "נשאר פתוח" in text
    chat.press(daily.task_button, "t:dry")
    assert "איזה עציץ נראה יבש" in chat.shown[-1]
    chat.press(daily.task_button, "t:dry:6")
    assert chat.shown[-1].startswith("🥀 רשמתי. #6")
    with chat.session() as s:
        assert find_container(s, USER, 6).water_adjust_days == -1


def test_nothing_to_do_is_one_line(chat):
    with chat.session() as s:
        for c in tasks.containers_in_map_order(s, USER):
            carelog.log(s, c, "water", source="button", commit=False)
            carelog.log(s, c, "feed", source="button", commit=False)
        s.commit()
        tasks.generate(s, USER, TODAY)
        text, kb = brief.morning(s, USER, TODAY)
    assert "אין משימות היום" in valid(text) and kb.inline_keyboard == ()


def test_jobs_send_messages(chat):
    bot = SimpleNamespace(send_message=AsyncMock())
    ctx = SimpleNamespace(application=chat.app, bot=bot, job=SimpleNamespace(data=USER))
    asyncio.run(daily.brief_job(ctx))
    asyncio.run(daily.evening_job(ctx))
    (chat_id, morning), _ = bot.send_message.call_args_list[0]
    (_, evening), _ = bot.send_message.call_args_list[1]
    assert chat_id == USER
    assert valid(morning).startswith("☀️") and valid(evening).startswith("🌙")
    with chat.session() as s:
        assert s.scalars(select(Task)).all()  # the morning job created the tasks


def test_settings_reschedules_jobs():
    factory = make_session_factory(make_engine("sqlite://"))
    app = build_application(Settings("123:TEST", frozenset({USER})), factory)
    daily.schedule_user(app, USER)
    job = app.job_queue.get_jobs_by_name(f"brief-{USER}")[0]
    assert job.callback is daily.brief_job
    chat = SimpleNamespace(shown=[])
    update = MagicMock()
    update.effective_user.id = USER
    update.callback_query.data = "st:b:0630"
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock(side_effect=lambda t, **k: chat.shown.append(t))
    asyncio.run(daily.settings_button(update, SimpleNamespace(application=app)))
    assert "06:30" in chat.shown[-1] and "✅ עודכן" in chat.shown[-1]
    with factory() as s:
        assert brief.get_settings(s, USER).brief_time == "06:30"


def test_time_pickers_use_15_minute_steps():
    assert "05:45" in brief.BRIEF_TIMES and "05:50" not in brief.BRIEF_TIMES  # 05:50 is only the default
    assert brief.BRIEF_TIMES[0] == "04:00" and brief.EVENING_TIMES[-1] == "22:00"


def test_care_overview_and_profile_buttons(chat):
    chat.command(care.care_cmd)
    text = chat.shown[-1]
    assert "אלוורה: מעט מים · סוקולנט" in text and "לא מזוהה: ❓ · ❓" in text
    assert "e:p:19" in chat.callbacks()


def test_all_screens_fit_telegram(chat):
    with chat.session() as s:
        tasks.generate(s, USER, TODAY)
        for text, kb in [
            brief.morning(s, USER, TODAY), brief.evening(s, USER, TODAY), brief.dry_picker(s, USER),
            brief.water_menu(s, USER, "w"), brief.water_pick(s, USER, "w"), brief.care_overview(s, USER),
            brief.settings_view(s, USER), brief.time_picker("b"), brief.time_picker("e"),
            brief.baseline_question(s, USER),
        ]:
            valid(text)
            cbs = [b.callback_data for row in kb.inline_keyboard for b in row]
            assert all(len(cb.encode()) <= 64 for cb in cbs) and len(cbs) <= 100
