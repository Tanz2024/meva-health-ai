"""Tests for MEVA's deterministic evidence verification layer.

Fully offline — no Ollama required. Claims are constructed by hand to
simulate what a local model's structured output might contain; the
verification logic itself is what's under test here.
"""

from meva.verification import MedicalClaim, build_ledger, build_report, verify_claim
from meva.verification.evidence import PatientNotFoundError
from meva.verification.scoring import summarize

# Stage 8A.1: repointed to the locally-generated public dataset (see
# data/synthetic/synthea/PROVENANCE.md) after the former sample-data-derived
# patients were removed for licensing reasons.
RICH_PATIENT_ID = "080b069b-5108-46b6-ecef-6aacd3b9ef3f"  # patient-20.json: allergies (incl. Fish (substance), criticality=low/clinical_status=active), conditions, medications, observations
SPARSE_PATIENT_ID = "d15b23ed-02d5-3e28-efbd-2604425317c5"  # patient-01.json: no allergies or medications
UNKNOWN_PATIENT_ID = "does-not-exist-999"


def claim(**kwargs) -> MedicalClaim:
    defaults = {"text": "test claim", "patient_id": RICH_PATIENT_ID, "assertion": "present"}
    defaults.update(kwargs)
    return MedicalClaim(**defaults)


# 1. Existing allergy claim -> SUPPORTED
def test_existing_allergy_claim_supported():
    ledger = build_ledger(RICH_PATIENT_ID)
    result = verify_claim(claim(category="allergy", value="Fish"), ledger)
    assert result.status == "SUPPORTED"
    assert len(result.evidence) == 1


# 2. Non-existing allergy claim -> UNSUPPORTED
def test_nonexistent_allergy_claim_unsupported():
    ledger = build_ledger(RICH_PATIENT_ID)
    result = verify_claim(claim(category="allergy", value="Latex"), ledger)
    assert result.status == "UNSUPPORTED"
    assert result.evidence == []


# 3. "No allergies" when allergies exist -> CONTRADICTED
def test_absent_allergy_claim_contradicted_when_allergies_exist():
    ledger = build_ledger(RICH_PATIENT_ID)
    result = verify_claim(claim(category="allergy", assertion="absent"), ledger)
    assert result.status == "CONTRADICTED"
    assert len(result.evidence) == 9  # patient-20 has 9 recorded allergies


# 4. "No allergies" when patient exists and list is genuinely empty -> SUPPORTED
def test_absent_allergy_claim_supported_when_list_empty():
    ledger = build_ledger(SPARSE_PATIENT_ID)
    result = verify_claim(claim(patient_id=SPARSE_PATIENT_ID, category="allergy", assertion="absent"), ledger)
    assert result.status == "SUPPORTED"


# 5. Unknown patient does NOT become "no allergies"
def test_unknown_patient_is_not_treated_as_no_allergies():
    result = verify_claim(claim(patient_id=UNKNOWN_PATIENT_ID, category="allergy", assertion="absent"), None)
    assert result.status == "UNVERIFIABLE"
    assert "not found" in result.reason.lower()


def test_build_ledger_raises_for_unknown_patient():
    try:
        build_ledger(UNKNOWN_PATIENT_ID)
        assert False, "expected PatientNotFoundError"
    except PatientNotFoundError:
        pass


# 6. Medication claim supported
def test_medication_claim_supported():
    ledger = build_ledger(RICH_PATIENT_ID)
    result = verify_claim(claim(category="medication", value="lisinopril"), ledger)
    assert result.status == "SUPPORTED"


# 7. Wrong medication unsupported
def test_wrong_medication_unsupported():
    ledger = build_ledger(RICH_PATIENT_ID)
    result = verify_claim(claim(category="medication", value="Metformin"), ledger)
    assert result.status == "UNSUPPORTED"


# 8. Condition claim supported
def test_condition_claim_supported():
    ledger = build_ledger(RICH_PATIENT_ID)
    result = verify_claim(claim(category="condition", value="Essential hypertension"), ledger)
    assert result.status == "SUPPORTED"


# 9. Blood pressure exact recorded value supported
def test_blood_pressure_exact_value_supported():
    ledger = build_ledger(RICH_PATIENT_ID)
    result = verify_claim(claim(category="observation", assertion="value", value="107/77 mmHg"), ledger)
    assert result.status == "SUPPORTED"
    assert len(result.evidence) == 1


# 10. Interpretation of blood pressure is UNVERIFIABLE
def test_blood_pressure_interpretation_unverifiable():
    ledger = build_ledger(RICH_PATIENT_ID)
    result = verify_claim(claim(category="observation", assertion="interpretation", value=None), ledger)
    assert result.status == "UNVERIFIABLE"


# 11. Evidence provenance attached
def test_evidence_provenance_attached():
    ledger = build_ledger(RICH_PATIENT_ID)
    result = verify_claim(claim(category="allergy", value="Fish"), ledger)
    ref = result.evidence[0]
    assert ref.source_tool == "get_allergies"
    assert ref.resource_id is not None
    assert "fish" in ref.value.lower()


# 12. Tool error not added to evidence ledger
def test_tool_error_not_added_to_evidence_ledger():
    # build_ledger raises for unknown patients rather than returning a ledger with a fake "error" fact.
    try:
        ledger = build_ledger(UNKNOWN_PATIENT_ID)
        assert not any(f.category == "error" for f in ledger.facts)
    except PatientNotFoundError:
        pass  # expected — no ledger, no evidence, no error masquerading as a fact


# 13. Empty evidence distinguished from error
def test_empty_evidence_distinguished_from_patient_not_found():
    empty_ledger = build_ledger(SPARSE_PATIENT_ID)
    assert empty_ledger.was_retrieved("allergy")
    assert empty_ledger.facts_for("allergy") == []

    try:
        build_ledger(UNKNOWN_PATIENT_ID)
        assert False, "expected PatientNotFoundError"
    except PatientNotFoundError:
        pass


# 14. Score calculated correctly
def test_score_calculated_correctly():
    claims = [
        claim(category="allergy", value="Fish"),          # SUPPORTED
        claim(category="allergy", value="Latex"),          # UNSUPPORTED
        claim(category="allergy", assertion="absent"),      # CONTRADICTED (allergies exist)
        claim(category="observation", assertion="interpretation"),  # UNVERIFIABLE
    ]
    report = build_report("test answer", claims)
    assert report.summary.verifiable_claims == 3
    assert report.summary.supported == 1
    assert report.summary.contradicted == 1
    assert report.summary.unsupported == 1
    assert report.summary.unverifiable == 1
    assert report.summary.grounding_score == "33%"


# 15. Zero verifiable claims returns N/A
def test_zero_verifiable_claims_returns_na():
    claims = [claim(category="observation", assertion="interpretation")]
    report = build_report("test answer", claims)
    assert report.summary.verifiable_claims == 0
    assert report.summary.grounding_score == "N/A"


def test_summarize_empty_list_returns_na():
    summary = summarize([])
    assert summary.grounding_score == "N/A"
    assert summary.verifiable_claims == 0


# 16. Normalization handles safe capitalization/display differences
def test_normalization_handles_case_and_display_suffix():
    ledger = build_ledger(RICH_PATIENT_ID)
    for value in ("fish", "FISH", "Fish", "fish (substance)", "  Fish  "):
        result = verify_claim(claim(category="allergy", value=value), ledger)
        assert result.status == "SUPPORTED", f"expected SUPPORTED for '{value}'"


# --- report-level checks -----------------------------------------------

def test_build_report_handles_multiple_patients_in_one_report():
    claims = [
        claim(patient_id=RICH_PATIENT_ID, category="allergy", value="Fish"),
        claim(patient_id=SPARSE_PATIENT_ID, category="allergy", assertion="absent"),
        claim(patient_id=UNKNOWN_PATIENT_ID, category="allergy", assertion="absent"),
    ]
    report = build_report("multi-patient answer", claims)
    statuses = [c.status for c in report.claims]
    assert statuses == ["SUPPORTED", "SUPPORTED", "UNVERIFIABLE"]


def test_unknown_claim_category_is_unverifiable():
    ledger = build_ledger(RICH_PATIENT_ID)
    result = verify_claim(claim(category="procedure", value="Something"), ledger)
    assert result.status == "UNVERIFIABLE"


# 17. Existing 40+ tests still pass — verified by running the full suite, not here.
