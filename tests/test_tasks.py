from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, inspect, select, text

from botnik import carelog, clock, tasks
from botnik.db import add_missing_columns, make_engine, make_session_factory
from botnik.editing import apply_answer, find_container
from botnik.models import CareEvent, Task
from botnik.seed import load_yaml, seed

USER = 111
TODAY = clock.today()


@pytest.fixture()
def s():
    with make_session_factory(make_engine("sqlite://"))() as session:
        seed(session, load_yaml(), USER)
        yield session


def c(s, n):
    return find_container(s, USER, n)


def water_all(s, days_ago):
    when = clock.utc_at_local(TODAY - timedelta(days=days_ago))
    for cont in tasks.containers_in_map_order(s, USER):
        carelog.log(s, cont, "water", source="baseline", at=when, commit=False)
    s.commit()


def open_water(s):
    return {t.container.number for t in tasks.actionable(s, USER, TODAY) if t.type == "water"}


# --- care log ---

def test_seed_fills_care_profile(s):
    assert c(s, 12).plants[0].water_need == "low"  # aloe
    assert c(s, 9).plants[0].water_need == "high"  # basil
    assert c(s, 19).plants[1].water_need is None  # unidentified


def test_log_and_last_date(s):
    carelog.log(s, c(s, 1), "water", source="button", at=clock.utc_at_local(TODAY - timedelta(days=2)))
    assert carelog.last_date(s, c(s, 1).id, "water") == TODAY - timedelta(days=2)
    assert carelog.last_dates(s, USER, "water") == {c(s, 1).id: TODAY - timedelta(days=2)}


def test_undo_removes_events_and_reopens_tasks(s):
    tasks.generate(s, USER, TODAY)
    batch = carelog.new_batch()
    carelog.log(s, c(s, 9), "water", source="button", batch=batch)
    assert 9 not in open_water(s)
    assert carelog.undo_batch(s, USER, batch) == 1
    assert 9 in open_water(s)
    assert carelog.undo_batch(s, USER, batch) == 0
    assert carelog.undo_batch(s, 999, batch) == 0  # other users can't undo


def test_move_logs_event_but_first_placement_does_not(s):
    apply_answer(s, c(s, 1), "slot", "P1")
    apply_answer(s, c(s, 24), "slot", "E1")  # #24 had no slot yet
    moves = s.scalars(select(CareEvent).where(CareEvent.type == "move")).all()
    assert [m.container_id for m in moves] == [c(s, 1).id]


# --- task generation ---

def test_no_history_everything_due_once(s):
    created = tasks.generate(s, USER, TODAY)
    assert len([t for t in created if t.type == "water"]) == 24
    assert tasks.generate(s, USER, TODAY) == []  # no duplicates


def test_after_watering_only_due_pots(s):
    water_all(s, 3)
    tasks.generate(s, USER, TODAY)
    due = open_water(s)
    assert 9 in due  # basil, high need: every 3 days (winter) at most
    assert 12 not in due  # aloe, low need
    assert 6 not in due  # bird of paradise, big pot


def test_complete_logs_water_and_closes(s):
    tasks.generate(s, USER, TODAY)
    task = next(t for t in tasks.actionable(s, USER, TODAY) if t.container.number == 9 and t.type == "water")
    tasks.complete(s, task)
    assert task.status == "done" and task.care_event_id
    event = s.get(CareEvent, task.care_event_id)
    assert event.type == "water" and event.source == "task" and event.amount_l > 0
    assert task in tasks.handled_today(s, USER, TODAY)
    assert tasks.generate(s, USER, TODAY) == []


def test_postpone_moves_to_tomorrow(s):
    tasks.generate(s, USER, TODAY)
    task = tasks.actionable(s, USER, TODAY)[0]
    tasks.postpone(s, task, TODAY)
    assert task not in tasks.actionable(s, USER, TODAY)
    assert task in tasks.actionable(s, USER, TODAY + timedelta(days=1))
    new = tasks.generate(s, USER, TODAY + timedelta(days=1))
    assert not any(t.container_id == task.container_id and t.type == task.type for t in new)  # no duplicate


def test_not_needed_teaches_and_waits(s):
    tasks.generate(s, USER, TODAY)
    task = next(t for t in tasks.actionable(s, USER, TODAY) if t.container.number == 9 and t.type == "water")
    tasks.not_needed(s, task)
    assert c(s, 9).water_adjust_days == 1
    assert not any(t.container.number == 9 and t.type == "water" for t in tasks.generate(s, USER, TODAY))
    # still not watered -> asked again tomorrow
    assert any(t.container.number == 9 and t.type == "water" for t in tasks.generate(s, USER, TODAY + timedelta(days=1)))


def test_feed_not_needed_waits_a_week(s):
    tasks.generate(s, USER, TODAY)
    task = next(t for t in tasks.actionable(s, USER, TODAY) if t.type == "feed")
    number = task.container.number
    tasks.not_needed(s, task)
    for days in range(1, 7):
        new = tasks.generate(s, USER, TODAY + timedelta(days=days))
        assert not any(t.container.number == number and t.type == "feed" for t in new)


def test_report_dry(s):
    water_all(s, 0)
    tasks.report_dry(s, c(s, 6), TODAY)
    assert c(s, 6).water_adjust_days == -1
    assert 6 in open_water(s)
    tasks.report_dry(s, c(s, 6), TODAY)  # no second task
    assert len([t for t in tasks.actionable(s, USER, TODAY) if t.container.number == 6]) == 1


def test_tomorrow_preview(s):
    water_all(s, 2)  # basil (#9, every 3 days) is due tomorrow
    assert (c(s, 9), "water") in tasks.tomorrow(s, USER, TODAY)


def test_no_feeding_in_winter_for_herbs(s):
    if clock.today().month not in (11, 12, 1, 2, 3):
        pytest.skip("winter-only expectation")
    created = tasks.generate(s, USER, TODAY)
    fed = {t.container.number for t in created if t.type == "feed"}
    assert 11 not in fed  # rosemary
    assert 1 in fed  # chrysanthemum, flowering


# --- migration ---

def test_add_missing_columns_keeps_data(tmp_path):
    """A Task-02 database (no care columns) opens with data intact and gains the new columns."""
    url = f"sqlite:///{tmp_path / 'old.db'}"
    engine = make_engine(url)
    with make_session_factory(engine)() as session:
        seed(session, load_yaml(), USER)
    with engine.begin() as conn:  # turn it back into the old schema
        conn.execute(text("ALTER TABLE plant DROP COLUMN water_need"))
        conn.execute(text("ALTER TABLE plant DROP COLUMN feed_group"))
        conn.execute(text("ALTER TABLE container DROP COLUMN water_adjust_days"))
    engine.dispose()

    engine = make_engine(url)  # what the bot does on startup
    cols = {col["name"] for col in inspect(engine).get_columns("plant")}
    assert {"water_need", "feed_group"} <= cols
    with engine.begin() as conn:
        assert conn.execute(text("SELECT count(*) FROM plant")).scalar() == 29
    assert add_missing_columns(engine) == []


def test_required_new_column_is_refused(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'odd.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE plant (id INTEGER PRIMARY KEY, name_he VARCHAR)"))
    with pytest.raises(RuntimeError):
        add_missing_columns(engine)
