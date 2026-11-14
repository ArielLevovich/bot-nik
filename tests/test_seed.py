from sqlalchemy import func, select

from botnik.db import make_engine, make_session_factory
from botnik.missing import missing_fields
from botnik.models import Container, Plant, Product, Slot
from botnik.seed import load_yaml, seed
from botnik.volume import estimate_container

USER = 111


def _counts(session):
    return {m.__tablename__: session.scalar(select(func.count()).select_from(m)) for m in (Slot, Container, Plant, Product)}


def _session():
    return make_session_factory(make_engine("sqlite://"))()


def test_seed_loads_the_garden():
    with _session() as s:
        seed(s, load_yaml(), USER)
        assert _counts(s) == {"slot": 15, "container": 24, "plant": 29, "product": 3}


def test_seed_twice_does_not_duplicate():
    data = load_yaml()
    with _session() as s:
        seed(s, data, USER)
        first = _counts(s)
        seed(s, data, USER)
        assert _counts(s) == first


def test_container_types_are_expanded():
    with _session() as s:
        seed(s, load_yaml(), USER)
        c2 = s.scalars(select(Container).filter_by(number=2)).one()
        assert c2.shape == "elliptical"
        assert (c2.outer_length_cm, c2.outer_width_cm, c2.outer_height_cm) == (60, 28, 25)
        assert c2.sections == ["A", "B"]
        assert c2.slot.code == "N3"
        assert [p.section for p in c2.plants] == ["A", "A", "B"]
        assert estimate_container(c2) is not None

        c3 = s.scalars(select(Container).filter_by(number=3)).one()
        assert c3.shape == "roundish" and c3.between_slot.code == "M4"
        assert c3.plants[0].section == "AB"  # planted in the center, over the divider
        assert estimate_container(c3) is not None


def test_missing_lists():
    # 2, 3, 4 and 7 were completed on 14.11.2026; 21-24 still wait for details; 19 has an unidentified plant.
    with _session() as s:
        seed(s, load_yaml(), USER)
        with_missing = sorted(c.number for c in s.scalars(select(Container)) if missing_fields(c))
        assert with_missing == [19, 21, 22, 23, 24]


def test_pest_profile_reaches_plants():
    with _session() as s:
        seed(s, load_yaml(), USER)
        hoya = s.scalars(select(Container).filter_by(number=21)).one().plants[0]
        assert hoya.pest_profile == "sensitive"
        assert hoya.pests_history == ["כנימה קמחית חוזרת"]


# --- Protection against re-seeding (Task 02, step 1) ---

import pytest

import botnik.seed as seed_module
from botnik.seed import has_garden, main, reset_garden


@pytest.fixture()
def cli_db(monkeypatch):
    """Run seed's main() against an in-memory DB for USER."""
    engine = make_engine("sqlite://")
    monkeypatch.setattr(seed_module, "make_engine", lambda: engine)
    monkeypatch.setattr(seed_module, "owner_user_id", lambda: USER)
    return make_session_factory(engine)


def _edit_container_1(factory):
    with factory() as s:
        c1 = s.scalars(select(Container).filter_by(number=1)).one()
        c1.condition = "edited in the bot"
        s.commit()


def _condition_1(factory):
    with factory() as s:
        return s.scalars(select(Container).filter_by(number=1)).one().condition


def test_first_run_loads(cli_db):
    main([])
    with cli_db() as s:
        assert has_garden(s, USER)
        assert _counts(s)["container"] == 24


def test_second_run_refuses_and_keeps_edits(cli_db):
    main([])
    _edit_container_1(cli_db)
    with pytest.raises(SystemExit) as exc:
        main([])
    assert "already in the database" in str(exc.value)
    assert _condition_1(cli_db) == "edited in the bot"


def test_reset_needs_yes(cli_db, monkeypatch):
    main([])
    _edit_container_1(cli_db)
    monkeypatch.setattr("builtins.input", lambda prompt="": "no")
    with pytest.raises(SystemExit):
        main(["--reset"])
    assert _condition_1(cli_db) == "edited in the bot"


def test_reset_with_yes_reloads_yaml(cli_db, monkeypatch):
    main([])
    _edit_container_1(cli_db)
    monkeypatch.setattr("builtins.input", lambda prompt="": "yes")
    main(["--reset"])
    assert _condition_1(cli_db) == "בפריחה"
    with cli_db() as s:
        assert _counts(s) == {"slot": 15, "container": 24, "plant": 29, "product": 3}


def test_reset_only_touches_one_user():
    with _session() as s:
        seed(s, load_yaml(), USER)
        seed(s, load_yaml(), 222)
        reset_garden(s, USER)
        assert not has_garden(s, USER)
        assert has_garden(s, 222)
