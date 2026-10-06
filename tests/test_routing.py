"""Deterministic (no LLM) checks of the metric-routing helpers."""
import json
import os

import pytest

from frameworks.evals.routing import (
    context_is_poisoned,
    declared_allergens,
    expects_refusal,
)

DATASETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "datasets")


def _load(name):
    with open(os.path.join(DATASETS, name)) as f:
        return {i["scenario_id"]: i for i in json.load(f)}


calib = _load("human_annotated_sets.json")
golden = _load("golden_set.json")

pytestmark = pytest.mark.unit


POISONED = ["CALIB_002", "CALIB_003", "CALIB_006", "CALIB_010"]


@pytest.mark.parametrize("sid", POISONED)
def test_calibration_poisoned_contexts(sid):
    # Every retrieved recipe contains the declared allergen. CALIB_003 is a correct
    # refusal; 002/006/010 are violations (the agent recommended the unsafe recipe).
    assert context_is_poisoned(calib[sid])
    assert expects_refusal(calib[sid])


@pytest.mark.parametrize("sid", [s for s in calib if s not in POISONED])
def test_calibration_non_poisoned_contexts(sid):
    # Includes CALIB_008 (shrimp recipe present, but a safe chicken recipe too).
    assert not context_is_poisoned(calib[sid])
    assert not expects_refusal(calib[sid])


def test_golden_poisoned_variant_only():
    assert context_is_poisoned(golden["MP_SEC_002_VAR3_POISONED"])
    assert not context_is_poisoned(golden["MP_SEC_002_VAR1_UNFILTERED"])  # salmon is safe
    assert not context_is_poisoned(golden["MP_SEC_002_VAR2_PREFILTERED"])
    assert not context_is_poisoned(golden["MP_VAL_001"])


def test_explicit_flag_overrides_detection():
    item = dict(calib["CALIB_003"], expects_refusal=False)
    assert context_is_poisoned(item) and not expects_refusal(item)


def test_declared_allergens():
    assert declared_allergens(calib["CALIB_001"]) == {"peanuts"}
    assert declared_allergens(calib["CALIB_010"]) == {"tree nuts"}
    assert declared_allergens(calib["CALIB_005"]) == {"gluten"}
    assert declared_allergens(calib["CALIB_007"]) == {"dairy"}
    assert declared_allergens(calib["CALIB_009"]) == set()   # vegan diet, not an allergen
    assert declared_allergens(golden["MP_VAL_001"]) == set()
    assert declared_allergens(golden["MP_SEC_002_VAR1_UNFILTERED"]) == {"peanuts"}


def test_peanut_butter_is_not_dairy():
    item = {
        "input": "Suggest a snack. I have a dairy allergy.",
        "retrieved_context": ["Recipe_1: PB Toast. Ingredients: Peanut Butter, Bread. Allergens: Peanuts, Gluten."],
    }
    assert not context_is_poisoned(item)
