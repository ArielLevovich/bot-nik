import re

import pytest

from botnik import labels
from botnik.db import make_engine, make_session_factory
from botnik.seed import load_yaml, seed
from botnik import views

USER = 111


@pytest.fixture()
def session():
    with make_session_factory(make_engine("sqlite://"))() as s:
        seed(s, load_yaml(), USER)
        yield s


def _numbers(text):
    return sorted(int(n) for n in re.findall(r"#(\d+)", text))


def test_overview_shows_all_24_containers(session):
    text, keyboard = views.garden_overview(session, USER)
    assert _numbers(text) == list(range(1, 25))
    assert "סה״כ 24 מיכלים" in text
    # One button per area that has containers, plus "no location" for #24.
    callbacks = [b.callback_data for row in keyboard.inline_keyboard for b in row]
    assert "g:a:main_railing" in callbacks and f"g:a:{labels.NO_SLOT_KEY}" in callbacks


def test_overview_places_containers_in_their_slots(session):
    text, _ = views.garden_overview(session, USER)
    assert re.search(r"P1 · 🟡 <b>#6</b> ציפור גן עדן", text)
    assert re.search(r"N3 · 🟡 <b>#2</b> רקפת ×3", text)
    assert re.search(r"M3 · 🟢 <b>#3</b> .*\(בין M3 ל־M4\)", text)


def test_other_users_see_nothing(session):
    text, _ = views.garden_overview(session, 999)
    assert "ריקה" in text


def test_area_view_has_container_buttons(session):
    text, keyboard = views.area_view(session, USER, "main_railing")
    callbacks = [b.callback_data for row in keyboard.inline_keyboard for b in row]
    assert "g:c:1:a" in callbacks
    assert callbacks[-1] == views.CB_HOME
    assert all(len(cb.encode()) <= 64 for cb in callbacks)


def test_card_with_volume(session):
    text, _ = views.container_card(session, USER, 2)
    assert "28.4 ליטר" in text
    assert "אורך 60 × רוחב 28 × גובה 25" in text
    assert "חסר" not in text


def test_card_without_measurements(session):
    text, _ = views.container_card(session, USER, 21)
    assert "אי אפשר לחשב" in text
    assert "מסלול מזיקים רגיש" in text
    assert "❓" in text and "צורה" in text


def test_missing_lists_21_to_24(session):
    text, keyboard = views.missing_view(session, USER)
    assert sorted(set(_numbers(text))) == [21, 22, 23, 24]
    callbacks = [b.callback_data for row in keyboard.inline_keyboard for b in row]
    assert callbacks == ["g:c:21:m", "g:c:22:m", "g:c:23:m", "g:c:24:m"]


def test_unknown_container(session):
    text, _ = views.container_card(session, USER, 99)
    assert "לא מצאתי" in text
