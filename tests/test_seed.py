from sqlalchemy import func, select

from botnik.db import make_engine, make_session_factory
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
        assert c2.outer_length_cm == 60 and c2.outer_width_cm is None
        assert c2.sections == ["A", "B"]
        assert c2.slot.code == "N3"
        assert [p.section for p in c2.plants] == ["A", "A", "B"]
        assert estimate_container(c2) is None  # width unknown

        c3 = s.scalars(select(Container).filter_by(number=3)).one()
        assert c3.shape == "roundish" and c3.between_slot.code == "M4"
        assert estimate_container(c3) is not None


def test_missing_lists():
    with _session() as s:
        seed(s, load_yaml(), USER)
        with_missing = sorted(c.number for c in s.scalars(select(Container)) if c.missing)
        assert with_missing == [2, 3, 4, 7, 21, 22, 23, 24]


def test_pest_profile_reaches_plants():
    with _session() as s:
        seed(s, load_yaml(), USER)
        hoya = s.scalars(select(Container).filter_by(number=21)).one().plants[0]
        assert hoya.pest_profile == "sensitive"
        assert hoya.pests_history == ["כנימה קמחית חוזרת"]
