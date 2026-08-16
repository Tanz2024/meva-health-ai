"""Tests for MEVA's benchmark dataset validator and the v0.1/v0.2 datasets themselves.

Fully offline — the validator never calls Ollama.
"""

import pytest

from meva.benchmark import load_cases
from meva.benchmark.models import BenchmarkCase
from meva.benchmark.validator import ValidationError, validate_case, validate_dataset

RICH_PATIENT_ID = "080b069b-5108-46b6-ecef-6aacd3b9ef3f"
INVALID_PATIENT_ID = "does-not-exist-999"


def test_v01_still_loads():
    cases = load_cases()  # default path is v0.1
    assert len(cases) == 12


def test_v02_loads():
    cases = load_cases(path="benchmarks/v0.2/cases.json")
    assert len(cases) == 40


def test_v03_loads():
    cases = load_cases(path="benchmarks/v0.3/cases.json")
    assert len(cases) == 56


@pytest.mark.skip(
    reason="v0.1's patients were removed in Stage 8A.1 (unlicensed synthea-sample-data "
    "provenance — see docs/historical-sample-data-provenance.md); live evidence "
    "re-validation is no longer possible for this historical dataset. v0.1 remains "
    "loadable (see test_v01_still_loads) and its historical results are preserved."
)
def test_v01_dataset_passes_validation():
    cases = load_cases()
    validate_dataset(cases)  # must not raise


@pytest.mark.skip(
    reason="v0.2's patients were removed in Stage 8A.1 (unlicensed synthea-sample-data "
    "provenance — see docs/historical-sample-data-provenance.md); live evidence "
    "re-validation is no longer possible for this historical dataset."
)
def test_v02_dataset_passes_validation():
    cases = load_cases(path="benchmarks/v0.2/cases.json")
    validate_dataset(cases)  # must not raise


@pytest.mark.skip(
    reason="v0.3's patients were removed in Stage 8A.1 (unlicensed synthea-sample-data "
    "provenance — see docs/historical-sample-data-provenance.md); live evidence "
    "re-validation is no longer possible for this historical dataset. v0.4 is the current "
    "live, fully-validated public dataset — see test_v04_dataset_passes_validation."
)
def test_v03_dataset_passes_validation():
    cases = load_cases(path="benchmarks/v0.3/cases.json")
    warnings = validate_dataset(cases)  # must not raise
    assert warnings == []


def test_v04_dataset_passes_validation():
    """v0.4 (Stage 8A.1) is the current live, publicly-committed dataset — built entirely
    from the locally-generated Apache-2.0 Synthea fixtures (see
    data/synthetic/synthea/PROVENANCE.md). Every expected_evidence_facts entry is checked
    against real, on-disk FHIR data, same as v0.1-v0.3 were checked before their source
    patients were removed."""
    cases = load_cases(path="benchmarks/v0.4/cases.json")
    warnings = validate_dataset(cases)  # must not raise
    assert warnings == []


def test_validator_accepts_valid_case():
    case = BenchmarkCase(
        case_id="valid-1", category="allergy", patient_id=RICH_PATIENT_ID,
        question="q", expected_tools=["get_allergies"], description="d",
        expected_evidence_facts=[{"category": "allergy", "value": "Fish", "source_tool": "get_allergies"}],
    )
    assert validate_case(case) == []


def test_duplicate_case_id_rejected():
    case_a = BenchmarkCase(case_id="dup", category="allergy", patient_id=RICH_PATIENT_ID, question="q", expected_tools=["get_allergies"], description="d")
    case_b = BenchmarkCase(case_id="dup", category="medication", patient_id=RICH_PATIENT_ID, question="q", expected_tools=["get_medications"], description="d")

    with pytest.raises(ValidationError, match="duplicate case_id"):
        validate_dataset([case_a, case_b])


def test_invalid_tool_rejected():
    case = BenchmarkCase(
        case_id="bad-tool", category="allergy", patient_id=RICH_PATIENT_ID,
        question="q", expected_tools=["delete_everything"], description="d",
    )
    errors = validate_case(case)
    assert any("unknown tool" in e for e in errors)


def test_nonexistent_expected_evidence_rejected():
    case = BenchmarkCase(
        case_id="bad-evidence", category="allergy", patient_id=RICH_PATIENT_ID,
        question="q", expected_tools=["get_allergies"], description="d",
        expected_evidence_facts=[{"category": "allergy", "value": "Zzznonexistentallergen", "source_tool": "get_allergies"}],
    )
    errors = validate_case(case)
    assert any("not found" in e for e in errors)


def test_invalid_patient_allowed_only_for_intentional_invalid_case():
    # correct: category is invalid_patient AND patient doesn't exist
    ok_case = BenchmarkCase(
        case_id="invalid-ok", category="invalid_patient", patient_id=INVALID_PATIENT_ID,
        question="q", expected_tools=["get_allergies"], description="d",
    )
    assert validate_case(ok_case) == []

    # wrong: patient doesn't exist but category isn't invalid_patient
    bad_case = BenchmarkCase(
        case_id="invalid-bad", category="allergy", patient_id=INVALID_PATIENT_ID,
        question="q", expected_tools=["get_allergies"], description="d",
    )
    errors = validate_case(bad_case)
    assert any("was not found" in e for e in errors)

    # wrong: category is invalid_patient but patient actually exists
    mislabeled_case = BenchmarkCase(
        case_id="invalid-mislabeled", category="invalid_patient", patient_id=RICH_PATIENT_ID,
        question="q", expected_tools=["get_allergies"], description="d",
    )
    errors = validate_case(mislabeled_case)
    assert any("actually exists" in e for e in errors)


def test_verifier_challenge_without_injected_claim_rejected():
    case = BenchmarkCase(
        case_id="vc-bad", category="verifier_challenge", case_type="VERIFIER_CHALLENGE",
        patient_id=RICH_PATIENT_ID, question="q", expected_tools=[], description="d",
    )
    errors = validate_case(case)
    assert any("must set injected_claim" in e for e in errors)


def test_unsafe_language_flagged():
    case = BenchmarkCase(
        case_id="unsafe-1", category="condition", patient_id=RICH_PATIENT_ID,
        question="What treatment should this patient receive?", expected_tools=["get_conditions"], description="d",
    )
    errors = validate_case(case)
    assert any("unsafe language" in e for e in errors)


# --- duplication audit (Stage 7B.5) -----------------------------------------

def test_exact_duplicate_case_rejected():
    case_a = BenchmarkCase(
        case_id="dup-a", category="allergy", patient_id=RICH_PATIENT_ID,
        question="Does the patient have a fish allergy?", expected_tools=["get_allergies"], description="d",
        expected_evidence_facts=[{"category": "allergy", "value": "Fish", "source_tool": "get_allergies", "resource_id": "abc"}],
    )
    case_b = BenchmarkCase(
        case_id="dup-b", category="allergy", patient_id=RICH_PATIENT_ID,
        question="Does the patient have a fish allergy?", expected_tools=["get_allergies"], description="d (different wording here)",
        expected_evidence_facts=[{"category": "allergy", "value": "Fish", "source_tool": "get_allergies", "resource_id": "abc"}],
    )
    with pytest.raises(ValidationError, match="exact duplicate"):
        validate_dataset([case_a, case_b])


def test_near_duplicate_case_only_warns():
    case_a = BenchmarkCase(
        case_id="near-a", category="allergy", patient_id=RICH_PATIENT_ID,
        question="What allergies are recorded?", expected_tools=["get_allergies"], description="d",
    )
    case_b = BenchmarkCase(
        case_id="near-b", category="medication", patient_id=RICH_PATIENT_ID,
        question="What allergies are recorded?", expected_tools=["get_medications"], description="d",
    )
    warnings = validate_dataset([case_a, case_b])  # must not raise — different category/tools, same wording
    assert any("possible semantic duplicate" in w for w in warnings)


def test_different_cases_produce_no_warnings():
    # v0.4 (see test_v04_dataset_passes_validation) — v0.3's patients were removed in
    # Stage 8A.1, so it can no longer be live-validated (see test_v03_dataset_passes_validation).
    cases = load_cases(path="benchmarks/v0.4/cases.json")
    warnings = validate_dataset(cases)
    assert warnings == []
