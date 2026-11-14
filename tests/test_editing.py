import pytest
from sqlalchemy import select

from botnik import editing
from botnik.db import make_engine, make_session_factory
from botnik.missing import missing_fields
from botnik.models import Container
from botnik.seed import load_yaml, seed
from botnik.volume import estimate_container

USER = 111


@pytest.fixture()
def session():
    with make_session_factory(make_engine("sqlite://"))() as s:
        seed(s, load_yaml(), USER)
        yield s


def container(s, n):
    return editing.find_container(s, USER, n)


# --- parse_number ---

@pytest.mark.parametrize(
    "text, value",
    [("30", 30), ("30.5", 30.5), ("30,5", 30.5), (" 18 ", 18), ("30 ס״מ", 30), ('30 ס"מ', 30), ("30סמ", 30), ("30cm", 30), ("12 CM", 12)],
)
def test_parse_number_ok(text, value):
    assert editing.parse_number(text) == value


@pytest.mark.parametrize("text", ["", "abc", "thirty", "10 × 12", "-5", "0", "301", "1e3"])
def test_parse_number_rejects(text):
    with pytest.raises(ValueError) as exc:
        editing.parse_number(text)
    assert str(exc.value)  # a Hebrew message for the owner


# --- next_key ---

def test_complete_mode_follows_missing_order(session):
    c = container(session, 22)
    assert editing.next_key(c, "c", [], []) == "shape"
    assert editing.next_key(c, "c", [], ["shape"]) == "material"  # "outer" can't be asked before the shape


def test_shape_answer_unlocks_its_dimensions(session):
    c = container(session, 22)
    editing.apply_answer(session, c, "shape", "round")
    assert editing.next_key(c, "c", [], []) == "outer.diameter"
    editing.apply_answer(session, c, "outer.diameter", 15.0)
    assert editing.next_key(c, "c", [], []) == "outer.height"


def test_fixed_modes(session):
    c = container(session, 1)
    queue = list(editing.FIXED_KEYS["m"])
    assert editing.next_key(c, "m", queue, []) == "slot"
    assert editing.next_key(c, "m", queue, []) == "level"
    assert editing.next_key(c, "m", queue, []) is None


def test_complete_container_has_nothing_to_ask(session):
    assert editing.next_key(container(session, 1), "c", [], []) is None


# --- apply_answer ---

def test_full_completion_of_23(session):
    c = container(session, 23)
    for key, value in [
        ("shape", "round"), ("outer.diameter", 20.0), ("outer.height", 15.0),
        ("material", "plastic"), ("color", "white"), ("condition", "פורח"),
    ]:
        assert editing.next_key(c, "c", [], []) == key
        editing.apply_answer(session, c, key, value)
    assert missing_fields(c) == []
    assert estimate_container(c).volume_l == pytest.approx(3.6, abs=0.1)


def test_answers_are_committed(session):
    c = container(session, 23)
    editing.apply_answer(session, c, "material", "ceramic")
    session.expire_all()
    assert container(session, 23).material == "ceramic"


def test_move_changes_slot_and_clears_between(session):
    c = container(session, 3)  # M3, between M3 and M4
    editing.apply_answer(session, c, "slot", "N2")
    assert c.slot.code == "N2" and c.between_slot_id is None


def test_status_updates_container_and_plants(session):
    c = container(session, 2)
    editing.apply_answer(session, c, "status", "needs_care")
    editing.apply_answer(session, c, "condition_update", "  עלים נבולים ")
    assert c.status == "needs_care" and c.condition == "עלים נבולים"
    assert {p.status for p in c.plants} == {"needs_care"}


def test_outer_raw_meaning_is_saved_and_cleared(session):
    c = container(session, 24)
    assert "outer_raw_meaning" in missing_fields(c)
    editing.apply_answer(session, c, "outer_raw_meaning", "קוטר 10, גובה 12")
    assert c.outer_raw == "10 × 12 – קוטר 10, גובה 12"
    assert "outer_raw_meaning" not in missing_fields(c)


def test_other_material_as_text(session):
    c = container(session, 21)
    editing.apply_answer(session, c, "material", "סל נצרים")
    assert c.material == "סל נצרים"


# --- questions ---

@pytest.mark.parametrize(
    "key", ["slot", "level", "shape", "outer.diameter", "material", "color", "condition", "condition_update", "status", "outer_raw_meaning"]
)
def test_every_question_renders(session, key):
    c = container(session, 24)
    q = editing.build_question(session, c, key)
    keyboard = editing.question_keyboard(q)
    callbacks = [b.callback_data for row in keyboard.inline_keyboard for b in row]
    assert editing.CB_SKIP in callbacks and editing.CB_CANCEL in callbacks
    assert all(len(cb.encode()) <= 64 for cb in callbacks)
    if q.kind == "choice":
        assert len([cb for cb in callbacks if cb.startswith("e:v:")]) == len(q.options)
    assert "#24" in editing.question_text(c, q)


def test_slot_question_lists_all_slots(session):
    q = editing.build_question(session, container(session, 24), "slot")
    assert [v for v, _ in q.options][:3] == ["M1", "M2", "M3"] and len(q.options) == 15


def test_card_shows_edit_buttons(session):
    from botnik import views

    _, kb = views.container_card(session, USER, 21)
    callbacks = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert {"e:c:21", "e:s:21", "e:m:21"} <= set(callbacks)
    _, kb = views.container_card(session, USER, 1)  # complete: no "complete details" button
    callbacks = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "e:c:1" not in callbacks and "e:s:1" in callbacks
