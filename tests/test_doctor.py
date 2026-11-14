"""Pest issues: database logic, daily-message integration, /doctor screens and photos."""

import asyncio
import io
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from PIL import Image
from sqlalchemy import select

from botnik import brief, clock, doctor, photos, tasks
from botnik.db import make_engine, make_session_factory
from botnik.editing import find_container
from botnik.handlers import daily
from botnik.handlers import doctor as doctor_handlers
from botnik.models import CareEvent, Photo, Task
from botnik.seed import load_yaml, seed

USER = 111
TODAY = clock.today()


@pytest.fixture()
def env(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'botnik.db'}")
    factory = make_session_factory(engine)
    with factory() as s:
        seed(s, load_yaml(), USER)
    return engine, factory


@pytest.fixture()
def s(env):
    with env[1]() as session:
        yield session


def c(s, n):
    return find_container(s, USER, n)


# --- the two "done when" cases ---

def test_hoya_mealybug_gets_confidor_drench(s):
    issue, note = doctor.open_issue(s, c(s, 21), None, "mealybug", "medium", flowering=False)
    assert note is None and issue.track == "sensitive"
    assert doctor.current_step(issue).action == "confidor"


def test_rosemary_mealybug_neem_in_the_evening_no_confidor(s):
    issue, _ = doctor.open_issue(s, c(s, 11), None, "mealybug", "medium", flowering=False)
    assert issue.track == "edible"
    actions = [st.action for st in doctor.plan(issue).steps]
    assert "confidor" not in actions and actions[:2] == ["remove", "neem"]


# --- steps, follow-ups, escalation ---

def test_do_step_logs_and_schedules_check(s):
    issue, _ = doctor.open_issue(s, c(s, 21), None, "mealybug", "medium", flowering=False)
    logged, message = doctor.do_step(s, issue, TODAY, now_local_hour=20)
    assert logged and issue.next_check == TODAY + timedelta(days=10)
    event = s.scalars(select(CareEvent).where(CareEvent.type == "drench")).one()
    assert event.product_id and "כנימה קמחית" in event.note


def test_neem_in_the_morning_gets_a_warning(s):
    issue, _ = doctor.open_issue(s, c(s, 1), None, "aphids", "heavy", flowering=False)  # strong + heavy: starts at neem
    assert doctor.current_step(issue).action == "neem"
    _, message = doctor.do_step(s, issue, TODAY, now_local_hour=9)
    assert "רק בערב" in message
    _, message = doctor.do_step(s, issue, TODAY, now_local_hour=19)
    assert "רק בערב" not in message


def test_check_task_appears_on_the_right_day(s):
    issue, _ = doctor.open_issue(s, c(s, 21), None, "mealybug", "medium", flowering=False)
    doctor.do_step(s, issue, TODAY, now_local_hour=20)
    before = tasks.generate(s, USER, TODAY + timedelta(days=9))
    assert not [t for t in before if t.type == "check"]
    on_day = tasks.generate(s, USER, TODAY + timedelta(days=10))
    assert [t.issue_id for t in on_day if t.type == "check"] == [issue.id]


def test_worse_moves_to_next_step_and_reminds(s):
    issue, _ = doctor.open_issue(s, c(s, 1), None, "aphids", "light", flowering=False)  # chrysanthemum: strong
    message = doctor.check_result(s, issue, "worse", TODAY)
    assert issue.step == 1 and "שלב 2" in message and "בסיכום הערב" in message  # neem: evening only
    treat = s.scalars(select(Task).where(Task.issue_id == issue.id, Task.type == "treat")).one()
    assert treat.evening_only
    assert treat not in tasks.actionable(s, USER, TODAY, evening=False)
    assert treat in tasks.actionable(s, USER, TODAY, evening=True)


def test_worse_stops_at_the_last_step(s):
    issue, _ = doctor.open_issue(s, c(s, 1), None, "root_rot", "light", flowering=False)
    for _ in range(10):
        doctor.check_result(s, issue, "worse", TODAY)
    assert doctor.current_step(issue).action == "nursery"


def test_clean_resolves_and_closes_tasks(s):
    issue, _ = doctor.open_issue(s, c(s, 1), None, "aphids", "light", flowering=False)
    doctor.remind_step(s, issue, TODAY)
    doctor.check_result(s, issue, "clean", TODAY)
    assert issue.status == "resolved"
    assert not s.scalars(select(Task).where(Task.issue_id == issue.id, Task.status == "open")).all()


def test_repeat_switches_to_sensitive(s):
    first, _ = doctor.open_issue(s, c(s, 1), None, "aphids", "light", flowering=False)
    doctor.resolve(s, first)
    second, note = doctor.open_issue(s, c(s, 1), None, "aphids", "light", flowering=False)
    assert "מסלול הרגיש" in note and second.track == "sensitive"
    assert all(p.pest_profile == "sensitive" for p in c(s, 1).plants)


def test_shared_soil_with_herb_means_no_confidor(s):
    # #8: sweet potato vine + bok choy (edible) share soil
    issue, _ = doctor.open_issue(s, c(s, 8), c(s, 8).plants[0], "aphids", "light", flowering=False)
    assert issue.track == "edible"


# --- pauses ---

def test_root_rot_pauses_watering_and_any_issue_pauses_feeding(s):
    doctor.open_issue(s, c(s, 1), None, "root_rot", "medium", flowering=False)
    doctor.open_issue(s, c(s, 2), None, "aphids", "light", flowering=False)
    created = tasks.generate(s, USER, TODAY)
    by = {(t.container.number, t.type) for t in created}
    assert (1, "water") not in by and (1, "feed") not in by and (2, "feed") not in by
    assert (2, "water") in by


def test_card_shows_issue_and_pause(s):
    from botnik import views

    doctor.open_issue(s, c(s, 1), None, "root_rot", "medium", flowering=False)
    text, kb = views.container_card(s, USER, 1)
    assert "מושהית" in text and "עובש שורשים" in text and "לא מדשנים כשיש בעיה פתוחה" in text
    assert any(b.callback_data.startswith("d:i:") for row in kb.inline_keyboard for b in row)


# --- daily messages ---

def test_check_buttons_in_brief(env, s):
    issue, _ = doctor.open_issue(s, c(s, 21), None, "mealybug", "medium", flowering=False)
    issue.next_check = TODAY
    s.commit()
    tasks.generate(s, USER, TODAY)
    text, kb = brief.morning(s, USER, TODAY)
    assert "🔍" in text and "כנימה קמחית: איך זה נראה?" in text
    cbs = [b.callback_data for row in kb.inline_keyboard for b in row]
    check_cb = next(cb for cb in cbs if cb.startswith("t:c:") and ":w:" in cb)

    shown = []
    update = MagicMock()
    update.effective_user.id = USER
    update.callback_query.data = check_cb
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock(side_effect=lambda t, **k: shown.append(t))
    ctx = SimpleNamespace(application=SimpleNamespace(bot_data={"session_factory": env[1]}))
    asyncio.run(daily.task_button(update, ctx))
    assert shown[-1].startswith("➡️ עוברים לשלב 2")


# --- /doctor screens ---

class Chat:
    def __init__(self, env):
        self.engine, self.factory = env
        self.context = SimpleNamespace(
            application=SimpleNamespace(bot_data={"session_factory": self.factory}), user_data={}, bot=MagicMock()
        )
        self.shown, self.keyboard, self.replies = [], None, []

    def _record(self, text, parse_mode=None, reply_markup=None):
        self.shown.append(text)
        self.keyboard = reply_markup

    def press(self, data):
        u = MagicMock()
        u.effective_user.id = USER
        u.callback_query.data = data
        u.callback_query.answer = AsyncMock()
        u.callback_query.edit_message_text = AsyncMock(side_effect=self._record)
        asyncio.run(doctor_handlers.on_button(u, self.context))

    def cbs(self):
        return [b.callback_data for row in self.keyboard.inline_keyboard for b in row] if self.keyboard else []

    def send_photo(self, data: bytes, caption=None):
        u = MagicMock()
        u.effective_user.id = USER
        u.effective_message.caption = caption
        u.effective_message.photo = [MagicMock(file_id="small"), MagicMock(file_id="big")]
        u.effective_message.reply_text = AsyncMock(side_effect=lambda t, **k: self.replies.append(t))
        tg_file = MagicMock()
        tg_file.download_as_bytearray = AsyncMock(return_value=bytearray(data))
        self.context.bot.get_file = AsyncMock(return_value=tg_file)
        asyncio.run(doctor_handlers.on_photo(u, self.context))


def test_doctor_flow_hoya(env):
    chat = Chat(env)
    chat.press("d:new")
    assert "d:p:21" in chat.cbs()
    chat.press("d:p:21")  # one plant: straight to symptoms
    assert "מה רואים" in chat.shown[-1]
    chat.press(next(cb for cb in chat.cbs() if cb.endswith(":mealybug")))
    assert "בלבול נפוץ" in chat.shown[-1]  # mealybug vs. mildew asked explicitly
    chat.press(next(cb for cb in chat.cbs() if cb.endswith(":mealybug")))
    chat.press(next(cb for cb in chat.cbs() if cb.endswith(":m")))
    assert "פורח עכשיו" in chat.shown[-1]
    chat.press(next(cb for cb in chat.cbs() if cb.endswith(":0")))
    plan_text = chat.shown[-1]
    assert "מסלול רגיש" in plan_text and "▶️ 1. קונפידור" in plan_text
    chat.press(next(cb for cb in chat.cbs() if cb.startswith("d:now:")))
    assert "✅ נרשם. בדיקה ב־" in chat.shown[-1] and "▶️ 1." in chat.shown[-1]


def test_doctor_edible_skips_flowering_question(env):
    chat = Chat(env)
    chat.press("d:p:11")
    chat.press("d:y:11:0:aphids")
    chat.press("d:v:11:0:aphids:l")
    assert "תוכנית" in chat.shown[-1] and "בלי קונפידור" in chat.shown[-1]


def test_doctor_multi_plant_and_mistake_delete(env):
    chat = Chat(env)
    chat.press("d:p:2")  # three cyclamens
    assert "על איזה צמח" in chat.shown[-1] and "d:s:2:a" in chat.cbs()
    chat.press("d:s:2:1")
    chat.press("d:y:2:1:spider_mites")
    chat.press("d:v:2:1:spider_mites:m")
    assert "אקריות" in chat.shown[-1]
    chat.press(next(cb for cb in chat.cbs() if cb.startswith("d:x:")))
    with env[1]() as s:
        assert doctor.open_issues(s, USER) == []


# --- photos ---

def jpeg_with_gps() -> bytes:
    img = Image.new("RGB", (3000, 2000), "green")
    exif = Image.Exif()
    exif[0x8825] = {2: (32.0, 10.0, 0.0), 4: (34.0, 54.0, 0.0)}  # GPSInfo: Kfar Saba-ish
    exif[0x010F] = "PhoneMaker"
    out = io.BytesIO()
    img.save(out, "JPEG", exif=exif)
    return out.getvalue()


def test_clean_image_strips_exif_and_resizes():
    raw = jpeg_with_gps()
    assert Image.open(io.BytesIO(raw)).getexif()
    cleaned = Image.open(io.BytesIO(photos.clean_image(raw)))
    assert not cleaned.getexif() and max(cleaned.size) == photos.MAX_SIDE


def test_caption_number():
    assert photos.container_from_caption("#21 עלים צהובים") == 21
    assert photos.container_from_caption("עציץ # 7") == 7
    assert photos.container_from_caption("בלי מספר") is None
    assert photos.container_from_caption(None) is None


def test_photo_with_caption_is_saved_and_linked(env):
    chat = Chat(env)
    with env[1]() as s:
        issue, _ = doctor.open_issue(s, c(s, 21), None, "mealybug", "medium", flowering=False)
    chat.send_photo(jpeg_with_gps(), caption="#21")
    assert "נשמר לעציץ #21" in chat.replies[-1] and "כנימה קמחית" in chat.replies[-1]
    with env[1]() as s:
        photo = s.scalars(select(Photo)).one()
        assert photo.issue_id == issue.id
        saved = Image.open(photos.file_for(env[0], photo))
        assert not saved.getexif()


def test_photo_without_caption_uses_last_doctor_pot_or_asks(env):
    chat = Chat(env)
    chat.send_photo(jpeg_with_gps())
    assert "לאיזה עציץ" in chat.replies[-1]
    chat.press("d:p:9")
    chat.send_photo(jpeg_with_gps())
    assert "נשמר לעציץ #9" in chat.replies[-1]


def test_card_photos_button(env):
    from botnik import views

    chat = Chat(env)
    chat.send_photo(jpeg_with_gps(), caption="#5")
    with env[1]() as s:
        _, kb = views.container_card(s, USER, 5)
    assert "ph:5" in [b.callback_data for row in kb.inline_keyboard for b in row]
