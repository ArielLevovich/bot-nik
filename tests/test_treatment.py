import itertools

import pytest

from botnik.pests import PESTS, SYMPTOMS
from botnik.treatment import confidor_refusal, plan_for, start_step

SUCKING = ["mealybug", "aphids", "whitefly"]


def products(plan):
    return [s.product for s in plan.steps]


@pytest.mark.parametrize(
    "pest, edible, sensitive, flowering", list(itertools.product(PESTS, [False, True], [False, True], [False, True]))
)
def test_policy_invariants(pest, edible, sensitive, flowering):
    plan = plan_for(pest, edible=edible, sensitive=sensitive, flowering=flowering)
    assert plan.steps, "every case has a plan"
    if "confidor" in products(plan):
        assert not edible and not flowering and PESTS[pest].confidor_ok
    for step in plan.steps:
        if step.product == "neem":
            assert step.evening_only
    assert plan.track == ("edible" if edible else "sensitive" if sensitive else "strong")


def test_never_confidor_for_mites_mildew_rot_leafminer():
    for pest in ("spider_mites", "mildew", "root_rot", "leafminer"):
        plan = plan_for(pest, edible=False, sensitive=True, flowering=False)
        assert "confidor" not in products(plan)
    assert any("פטרייה" in n for n in plan_for("mildew", edible=False, sensitive=False, flowering=False).notes)


def test_strong_plant_neem_rounds_before_confidor():
    plan = plan_for("mealybug", edible=False, sensitive=False, flowering=False)
    assert [s.action for s in plan.steps] == ["remove", "neem", "neem", "neem", "confidor", "nursery"]


def test_sensitive_plant_confidor_first():
    plan = plan_for("mealybug", edible=False, sensitive=True, flowering=False)
    assert plan.steps[0].action == "confidor" and "קונפידור הוא הטיפול העיקרי" in " ".join(plan.notes)


def test_sensitive_but_flowering_waits_for_confidor():
    plan = plan_for("mealybug", edible=False, sensitive=True, flowering=True)
    assert "confidor" not in products(plan) and any("דבורים" in n for n in plan.notes)


@pytest.mark.parametrize("pest", SUCKING)
def test_edible_never_confidor(pest):
    plan = plan_for(pest, edible=True, sensitive=True, flowering=False)
    assert "confidor" not in products(plan) and any("מאכל" in n for n in plan.notes)


def test_heavy_on_strong_skips_to_neem():
    strong = plan_for("aphids", edible=False, sensitive=False, flowering=False)
    assert start_step(strong, "heavy") == 1 and start_step(strong, "light") == 0
    sensitive = plan_for("aphids", edible=False, sensitive=True, flowering=False)
    assert start_step(sensitive, "heavy") == 0


def test_confidor_refusal_reasons():
    assert "מאכל" in confidor_refusal(edible=True, flowering=False, pest_key="mealybug")
    assert "פריחה" in confidor_refusal(edible=False, flowering=True, pest_key="mealybug")
    assert "לא עובד" in confidor_refusal(edible=False, flowering=False, pest_key="spider_mites")
    assert confidor_refusal(edible=False, flowering=False, pest_key="mealybug") is None


def test_every_symptom_maps_to_a_pest():
    assert {key for key, _ in SYMPTOMS} == set(PESTS)
