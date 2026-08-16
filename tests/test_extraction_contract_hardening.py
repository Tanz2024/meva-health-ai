"""Stage 7D2.1 tests: extraction contract examples, dev/holdout fixture separation,
prompt versioning/hashing, deterministic error classification, and the stricter
holdout decision gate. Fully offline — no Ollama required.
"""

import json
from pathlib import Path

from meva.extraction.extractor import _claim_is_valid
from meva.extraction.fidelity import (
    HOLDOUT_MIN_ATTRIBUTE_ACCURACY,
    HOLDOUT_MIN_F1,
    HOLDOUT_MIN_NEGATIVE_PRESERVATION,
    HOLDOUT_MIN_PRECISION,
    HOLDOUT_MIN_RECALL,
    classify_mismatches,
    passes_holdout_gate,
)
from meva.extraction.prompt import EXTRACTION_PROMPT_VERSION, EXTRACTION_SYSTEM_PROMPT, build_extraction_messages, prompt_hash
from meva.verification.models import MedicalClaim

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "extraction"


def _claim(**kw):
    base = dict(text="t", patient_id="p1", category="allergy", value="Fish", assertion="present")
    base.update(kw)
    return MedicalClaim(**base)


# --- 1. extraction contract examples parse per the documented rules ---------

def test_contract_global_absent_example_has_null_value():
    claim = MedicalClaim(text="t", patient_id="p1", category="allergy", value=None, assertion="absent")
    assert claim.value is None


def test_contract_item_specific_absent_example_has_item_value():
    claim = MedicalClaim(text="t", patient_id="p1", category="allergy", value="Penicillin", assertion="absent")
    assert claim.value == "Penicillin"


def test_contract_attribute_example_has_all_four_fields():
    claim = MedicalClaim(text="t", patient_id="p1", category="allergy", value="Fish", assertion="attribute",
                          attribute="criticality", attribute_value="low")
    assert claim.attribute == "criticality" and claim.attribute_value == "low"


# --- 2. global absent claim ---------------------------------------------------

def test_global_absent_claim_distinguished_from_item_specific():
    global_absent = _claim(category="allergy", value=None, assertion="absent")
    item_absent = _claim(category="allergy", value="Penicillin", assertion="absent")
    assert global_absent != item_absent
    assert global_absent.value is None
    assert item_absent.value == "Penicillin"


# --- 3. item-specific absent claim -------------------------------------------

def test_item_specific_absent_claim_requires_value_for_matching():
    from meva.extraction.fidelity import claim_key
    a = _claim(category="allergy", value="Penicillin", assertion="absent")
    b = _claim(category="allergy", value=None, assertion="absent")
    assert claim_key(a) != claim_key(b)


# --- 4. observation value claim ----------------------------------------------

def test_observation_value_claim_uses_value_assertion_not_present():
    claim = _claim(category="observation", value="Heart Rate: 72 bpm", assertion="value")
    assert claim.assertion == "value"
    assert "72 bpm" in claim.value


# --- 5. attribute claim -------------------------------------------------------

def test_attribute_claim_requires_attribute_and_attribute_value_to_be_valid():
    valid = {"text": "t", "category": "allergy", "value": "Fish", "assertion": "attribute", "attribute": "criticality", "attribute_value": "low", "patient_id": "p1"}
    invalid = {"text": "t", "category": "allergy", "value": "Fish", "assertion": "attribute", "attribute": None, "attribute_value": None, "patient_id": "p1"}
    assert _claim_is_valid(MedicalClaim(**valid)) is True
    assert _claim_is_valid(MedicalClaim(**invalid)) is False


# --- 6. multiple facts produce multiple expected claims -----------------------

def test_holdout_two_claim_fixture_has_two_expected_claims():
    fixtures = json.loads((DATA_DIR / "holdout_fixtures.json").read_text())
    fixture = next(f for f in fixtures if f["id"] == "holdout-two-claim-answer")
    assert len(fixture["expected_claims"]) == 2


def test_holdout_three_plus_claim_fixture_has_at_least_three_expected_claims():
    fixtures = json.loads((DATA_DIR / "holdout_fixtures.json").read_text())
    fixture = next(f for f in fixtures if f["id"] == "holdout-three-plus-claim-answer")
    assert len(fixture["expected_claims"]) >= 3


# --- 7. uncertain statement policy --------------------------------------------

def test_uncertain_fixtures_expect_zero_claims():
    for path in (DATA_DIR / "dev_fixtures.json", DATA_DIR / "holdout_fixtures.json"):
        fixtures = json.loads(path.read_text())
        for f in fixtures:
            if "uncertain" in f["id"]:
                assert f["expected_claims"] == [], f"{f['id']} in {path.name} should expect zero claims"


# --- 8. development/holdout separation ----------------------------------------

def test_dev_and_holdout_fixtures_have_disjoint_ids():
    dev = json.loads((DATA_DIR / "dev_fixtures.json").read_text())
    holdout = json.loads((DATA_DIR / "holdout_fixtures.json").read_text())
    dev_ids = {f["id"] for f in dev}
    holdout_ids = {f["id"] for f in holdout}
    assert not (dev_ids & holdout_ids)


def test_original_gold_fixtures_untouched():
    gold = json.loads((DATA_DIR / "gold_fixtures.json").read_text())
    dev = json.loads((DATA_DIR / "dev_fixtures.json").read_text())
    assert gold == dev  # dev_fixtures.json is a traceable copy of the original gold set


# --- 9. holdout fixture validation --------------------------------------------

def test_holdout_fixtures_schema_valid_and_cover_required_categories():
    fixtures = json.loads((DATA_DIR / "holdout_fixtures.json").read_text())
    assert 12 <= len(fixtures) <= 15
    for f in fixtures:
        assert {"id", "question", "patient_id", "answer", "expected_claims"} <= set(f)
        for raw_claim in f["expected_claims"]:
            MedicalClaim(**raw_claim)  # raises if malformed

    required_substrings = [
        "positive-allergy", "global-negative-allergy", "item-specific-negative-allergy",
        "medication-present", "condition-present", "observation-numeric-value",
        "observation-absence", "patient-demographic-fact", "attribute-criticality",
        "attribute-clinical-status", "two-claim-answer", "three-plus-claim-answer",
        "uncertain-statement", "no-factual-claim",
    ]
    ids = " ".join(f["id"] for f in fixtures)
    for needle in required_substrings:
        assert needle in ids, f"missing holdout coverage for: {needle}"


def test_holdout_fixtures_use_synthetic_patient_ids_only():
    fixtures = json.loads((DATA_DIR / "holdout_fixtures.json").read_text())
    for f in fixtures:
        assert f["patient_id"].startswith("fixture-")


# --- 10. prompt hash/versioning -----------------------------------------------

def test_prompt_hash_is_deterministic_and_matches_current_prompt():
    import hashlib
    expected = hashlib.sha256(EXTRACTION_SYSTEM_PROMPT.encode("utf-8")).hexdigest()
    assert prompt_hash() == expected
    assert prompt_hash() == prompt_hash()  # deterministic across calls


def test_prompt_version_is_a_non_empty_string():
    assert isinstance(EXTRACTION_PROMPT_VERSION, str) and EXTRACTION_PROMPT_VERSION


# --- 11. deterministic malformed-claim rejection -------------------------------

def test_malformed_attribute_claim_rejected_not_repaired():
    malformed = MedicalClaim(text="t", patient_id="p1", category="allergy", value="Fish",
                              assertion="attribute", attribute=None, attribute_value=None)
    assert _claim_is_valid(malformed) is False
    # rejection must not mutate the claim
    assert malformed.attribute is None and malformed.attribute_value is None


# --- 12. validator does not repair claims --------------------------------------

def test_validator_never_fills_in_missing_values():
    missing_value = MedicalClaim(text="t", patient_id="p1", category="allergy", value=None, assertion="present")
    assert _claim_is_valid(missing_value) is False
    assert missing_value.value is None  # still None — nothing was filled in


# --- 13. anti-leakage remains enforced ------------------------------------------

def test_anti_leakage_still_enforced_after_prompt_hardening():
    messages = build_extraction_messages("q", "p1", "No blood pressure was found.")
    full_text = " ".join(m["content"] for m in messages).lower()
    for forbidden in ("fhir", "evidencefact", "expected_evidence", "expected_status", "bundle"):
        assert forbidden not in full_text


# --- 14-18. holdout decision gate -----------------------------------------------

def _passing_metrics():
    return {
        "claim_precision": HOLDOUT_MIN_PRECISION, "claim_recall": HOLDOUT_MIN_RECALL,
        "claim_f1": HOLDOUT_MIN_F1, "negative_claim_preservation_rate": HOLDOUT_MIN_NEGATIVE_PRESERVATION,
        "attribute_claim_accuracy": HOLDOUT_MIN_ATTRIBUTE_ACCURACY,
    }


def test_holdout_gate_passes_correct_metrics():
    result = passes_holdout_gate(_passing_metrics())
    assert result["passed"] is True


def test_holdout_gate_fails_low_precision():
    metrics = _passing_metrics()
    metrics["claim_precision"] = HOLDOUT_MIN_PRECISION - 0.1
    result = passes_holdout_gate(metrics)
    assert result["passed"] is False
    assert result["claim_precision"] is False


def test_holdout_gate_fails_low_recall():
    metrics = _passing_metrics()
    metrics["claim_recall"] = HOLDOUT_MIN_RECALL - 0.1
    result = passes_holdout_gate(metrics)
    assert result["passed"] is False
    assert result["claim_recall"] is False


def test_holdout_gate_fails_poor_negative_preservation():
    metrics = _passing_metrics()
    metrics["negative_claim_preservation_rate"] = HOLDOUT_MIN_NEGATIVE_PRESERVATION - 0.2
    result = passes_holdout_gate(metrics)
    assert result["passed"] is False
    assert result["negative_claim_preservation_rate"] is False


def test_holdout_gate_fails_poor_attribute_accuracy():
    metrics = _passing_metrics()
    metrics["attribute_claim_accuracy"] = HOLDOUT_MIN_ATTRIBUTE_ACCURACY - 0.2
    result = passes_holdout_gate(metrics)
    assert result["passed"] is False
    assert result["attribute_claim_accuracy"] is False


def test_holdout_gate_treats_missing_metric_as_failing():
    metrics = _passing_metrics()
    metrics["claim_f1"] = None
    result = passes_holdout_gate(metrics)
    assert result["claim_f1"] is False
    assert result["passed"] is False


# --- 19. error classification ---------------------------------------------------

def test_classify_mismatches_wrong_assertion():
    gold = [_claim(category="allergy", value="Fish", assertion="present")]
    extracted = [_claim(category="allergy", value="Fish", assertion="absent")]
    errors = classify_mismatches("f1", gold, extracted)
    assert len(errors) == 1
    assert errors[0]["type"] == "wrong_assertion"


def test_classify_mismatches_wrong_value():
    gold = [_claim(category="allergy", value="Fish", assertion="present")]
    extracted = [_claim(category="allergy", value="Peanut", assertion="present")]
    errors = classify_mismatches("f1", gold, extracted)
    assert errors[0]["type"] == "wrong_value"


def test_classify_mismatches_wrong_category():
    gold = [_claim(category="allergy", value="Fish", assertion="present")]
    extracted = [_claim(category="medication", value="Fish", assertion="present")]
    errors = classify_mismatches("f1", gold, extracted)
    assert errors[0]["type"] == "wrong_category"


def test_classify_mismatches_attribute_error():
    gold = [_claim(category="allergy", value="Fish", assertion="attribute", attribute="criticality", attribute_value="high")]
    extracted = [_claim(category="allergy", value="Fish", assertion="attribute", attribute="criticality", attribute_value="low")]
    errors = classify_mismatches("f1", gold, extracted)
    assert errors[0]["type"] == "attribute_error"


def test_classify_mismatches_missed_claim_when_nothing_resembles_it():
    gold = [_claim(category="allergy", value="Fish", assertion="present")]
    extracted = []
    errors = classify_mismatches("f1", gold, extracted)
    assert errors[0]["type"] == "missed_claim"


def test_classify_mismatches_added_claim_when_extra_and_no_gold():
    gold = []
    extracted = [_claim(category="allergy", value="Fish", assertion="present")]
    errors = classify_mismatches("f1", gold, extracted)
    assert errors[0]["type"] == "added_claim"


def test_classify_mismatches_uncertainty_error_for_uncertain_fixture():
    gold = []
    extracted = [_claim(category="condition", value="Hypertension", assertion="present")]
    errors = classify_mismatches("holdout-uncertain-statement", gold, extracted)
    assert errors[0]["type"] == "uncertainty_error"
