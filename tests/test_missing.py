from types import SimpleNamespace

import pytest
from sqlalchemy import select

from botnik.db import make_engine, make_session_factory
from botnik.missing import extras_from_yaml, missing_fields
from botnik.models import Container
from botnik.seed import load_yaml, seed

COMPLETE = dict(
    slot_id=1,
    level="shelf",
    material="plastic",
    color="black",
    condition="ok",
    outer_diameter_cm=None,
    outer_length_cm=None,
    outer_width_cm=None,
    outer_height_cm=None,
    missing_extra=[],
)


def pot(**kw):
    return SimpleNamespace(**{**COMPLETE, **kw})


def test_complete_round_pot_has_nothing_missing():
    assert missing_fields(pot(shape="round", outer_diameter_cm=30, outer_height_cm=22)) == []


@pytest.mark.parametrize("shape", ["round", "roundish"])
def test_round_shapes_need_diameter_and_height(shape):
    assert missing_fields(pot(shape=shape)) == ["outer.diameter", "outer.height"]
    assert missing_fields(pot(shape=shape, outer_diameter_cm=30)) == ["outer.height"]


@pytest.mark.parametrize("shape", ["rectangular", "elliptical"])
def test_long_shapes_need_length_width_height(shape):
    assert missing_fields(pot(shape=shape)) == ["outer.length", "outer.width", "outer.height"]
    assert missing_fields(pot(shape=shape, outer_length_cm=60, outer_height_cm=25)) == ["outer.width"]


def test_round_pot_does_not_ask_for_width():
    # A diameter makes length/width irrelevant.
    assert "outer.width" not in missing_fields(pot(shape="round", outer_diameter_cm=20, outer_height_cm=10))


def test_unknown_shape_asks_shape_then_generic_dimensions():
    assert missing_fields(pot(shape=None)) == ["shape", "outer"]


def test_everything_missing_in_asking_order():
    empty = SimpleNamespace(
        slot_id=None, level=None, shape=None, material=None, color=None, condition=None,
        outer_diameter_cm=None, outer_length_cm=None, outer_width_cm=None, outer_height_cm=None,
        missing_extra=["outer_raw_meaning"],
    )
    assert missing_fields(empty) == [
        "slot", "level", "shape", "outer", "material", "color", "condition", "outer_raw_meaning",
    ]


def test_blank_condition_counts_as_missing():
    assert missing_fields(pot(shape="round", outer_diameter_cm=20, outer_height_cm=10, condition="  ")) == ["condition"]


def test_extras_that_duplicate_core_fields_are_ignored():
    p = pot(shape="round", outer_diameter_cm=20, outer_height_cm=10, missing_extra=["shape", "outer.width", "note_x"])
    assert missing_fields(p) == ["note_x"]


def test_extras_from_yaml_keeps_only_non_derivable():
    assert extras_from_yaml(["outer.width", "shape", "outer", "outer_raw_meaning", "section_assignment_by_color"]) == [
        "outer_raw_meaning",
        "section_assignment_by_color",
    ]


def test_real_garden():
    with make_session_factory(make_engine("sqlite://"))() as s:
        seed(s, load_yaml(), 111)
        by_number = {c.number: missing_fields(c) for c in s.scalars(select(Container))}
    # 19: its second plant is unidentified, so the care catalog can't fill its profile.
    assert [n for n, m in sorted(by_number.items()) if m] == [19, 21, 22, 23, 24]
    assert by_number[19] == ["plant1.water_need", "plant1.feed_group"]
    assert by_number[21] == ["level", "shape", "outer", "material", "color", "condition"]
    assert by_number[22] == ["shape", "outer", "material", "color", "condition"]
    assert by_number[24] == ["slot", "level", "shape", "outer", "material", "condition", "outer_raw_meaning"]
