"""Stage 8G — Guided Mode logic tests (meva.playground.guided).

Fully offline. Confirms every guided option maps to a claim shape the real,
unmodified deterministic verifier already supports, uses only real v0.4
evidence, and never invents a new assertion/category combination. No AI
model, no network, no chat.
"""

from pathlib import Path

from meva.playground import (
    GUIDED_CATEGORIES,
    GUIDED_RESULT_EXPLANATIONS,
    guided_custom_claim,
    guided_options,
    verify_claim,
)
from meva.verification.models import CLAIM_ASSERTIONS

ALLERGY_PATIENT_ID = "c053e996-a4c4-6c02-e2b6-284227156c67"
REPO_ROOT = Path(__file__).resolve().parent.parent


# --- guided category coverage -----------------------------------------------

def test_guided_categories_cover_the_five_specified_groups():
    categories = {cat for cat, _ in GUIDED_CATEGORIES}
    assert categories == {"allergy", "medication", "condition", "observation", "patient"}


# --- allergy mapping ---------------------------------------------------------

def test_guided_allergy_options_map_to_valid_claims():
    options = guided_options(ALLERGY_PATIENT_ID, "allergy")
    assert 2 <= len(options) <= 4
    for option in options:
        assert option["assertion"] in CLAIM_ASSERTIONS
        result = verify_claim(ALLERGY_PATIENT_ID, "allergy", option["assertion"], value=option["value"])
        assert result["status"] in ("SUPPORTED", "CONTRADICTED", "UNSUPPORTED", "UNVERIFIABLE")


def test_guided_allergy_recorded_option_uses_real_evidence():
    options = guided_options(ALLERGY_PATIENT_ID, "allergy")
    recorded = next(o for o in options if o["label"].endswith("allergy is recorded"))
    result = verify_claim(ALLERGY_PATIENT_ID, "allergy", recorded["assertion"], value=recorded["value"])
    assert result["status"] == "SUPPORTED"


# --- medication mapping -------------------------------------------------------

def test_guided_medication_options_map_to_valid_claims():
    options = guided_options(ALLERGY_PATIENT_ID, "medication")
    for option in options:
        assert option["assertion"] in CLAIM_ASSERTIONS
        verify_claim(ALLERGY_PATIENT_ID, "medication", option["assertion"], value=option["value"])


# --- condition mapping ---------------------------------------------------------

def test_guided_condition_options_map_to_valid_claims():
    options = guided_options(ALLERGY_PATIENT_ID, "condition")
    for option in options:
        assert option["assertion"] in CLAIM_ASSERTIONS
        verify_claim(ALLERGY_PATIENT_ID, "condition", option["assertion"], value=option["value"])


# --- observation mapping --------------------------------------------------------

def test_guided_observation_options_map_to_valid_claims():
    options = guided_options(ALLERGY_PATIENT_ID, "observation")
    for option in options:
        assert option["assertion"] in ("value", "absent")
        verify_claim(ALLERGY_PATIENT_ID, "observation", option["assertion"], value=option["value"])


def test_guided_observation_recorded_reading_uses_real_evidence():
    options = guided_options(ALLERGY_PATIENT_ID, "observation")
    recorded = next(o for o in options if o["label"].startswith("The recorded"))
    result = verify_claim(ALLERGY_PATIENT_ID, "observation", recorded["assertion"], value=recorded["value"])
    assert result["status"] == "SUPPORTED"


# --- patient info mapping -------------------------------------------------------

def test_guided_patient_options_only_expose_gender_and_birth_date():
    options = guided_options(ALLERGY_PATIENT_ID, "patient")
    for option in options:
        assert "gender" in option["label"].lower() or "birth date" in option["label"].lower()
        result = verify_claim(ALLERGY_PATIENT_ID, "patient", option["assertion"], value=option["value"])
        assert result["status"] == "SUPPORTED"


# --- suggested claims use real evidence, no unsupported combinations ---------

def test_all_guided_options_across_categories_use_real_v04_evidence():
    """Every suggested claim for every category must verify cleanly (never raise) —
    this is the "do not expose unsupported claim combinations" requirement."""
    for category, _ in GUIDED_CATEGORIES:
        for option in guided_options(ALLERGY_PATIENT_ID, category):
            verify_claim(ALLERGY_PATIENT_ID, category, option["assertion"], value=option["value"])


def test_guided_custom_claim_uses_present_for_presence_categories():
    claim = guided_custom_claim("allergy", "Fish")
    assert claim["assertion"] == "present"
    assert claim["value"] == "Fish"


def test_guided_custom_claim_uses_value_for_observation():
    claim = guided_custom_claim("observation", "120/80 mmHg")
    assert claim["assertion"] == "value"


# --- plain-English result descriptions --------------------------------------

def test_guided_result_explanations_cover_all_four_statuses():
    assert set(GUIDED_RESULT_EXPLANATIONS) == {"SUPPORTED", "CONTRADICTED", "UNSUPPORTED", "UNVERIFIABLE"}
    for text in GUIDED_RESULT_EXPLANATIONS.values():
        for forbidden in ("TRUE", "FALSE", "CORRECT DIAGNOSIS"):
            assert forbidden not in text.upper()


# --- no model inference / no paid or cloud APIs -------------------------------

def test_guided_module_never_imports_ollama_or_extraction():
    source = (REPO_ROOT / "src" / "meva" / "playground" / "guided.py").read_text()
    lowered = source.lower()
    for forbidden in ("ollama", "openai", "anthropic", "extraction"):
        assert forbidden not in lowered
