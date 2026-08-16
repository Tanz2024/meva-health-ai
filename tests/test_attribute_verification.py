"""Tests for Stage 7B.5's attribute-level evidence/claim/verification support.

Fully offline. This is the fix for the Stage 7B finding: an allergy's
criticality/clinical_status (and similar metadata fields already
returned by MEVA's tools) were previously unverifiable, so factually
correct model claims about them were wrongly scored UNSUPPORTED.
"""

from meva.ai.agent import _parse_agent_answer
from meva.verification import build_ledger, build_report
from meva.verification.evidence import EvidenceFact
from meva.verification.models import MedicalClaim
from meva.verification.verifier import verify_claim

# Stage 8A.1: repointed to the locally-generated public dataset (see
# data/synthetic/synthea/PROVENANCE.md).
RICH_PATIENT_ID = "080b069b-5108-46b6-ecef-6aacd3b9ef3f"  # patient-20.json: Fish (substance) allergy, criticality=low, clinical_status=active


def attribute_claim(**kwargs) -> MedicalClaim:
    defaults = {
        "text": "test", "patient_id": RICH_PATIENT_ID, "category": "allergy",
        "value": "Fish", "assertion": "attribute",
    }
    defaults.update(kwargs)
    return MedicalClaim(**defaults)


# 1. allergy criticality correct -> SUPPORTED
def test_allergy_criticality_correct_supported():
    ledger = build_ledger(RICH_PATIENT_ID)
    result = verify_claim(attribute_claim(attribute="criticality", attribute_value="low"), ledger)
    assert result.status == "SUPPORTED"


# 2. allergy criticality wrong -> CONTRADICTED
def test_allergy_criticality_wrong_contradicted():
    ledger = build_ledger(RICH_PATIENT_ID)
    result = verify_claim(attribute_claim(attribute="criticality", attribute_value="high"), ledger)
    assert result.status == "CONTRADICTED"


# 3. allergy clinical status correct -> SUPPORTED
def test_allergy_clinical_status_correct_supported():
    ledger = build_ledger(RICH_PATIENT_ID)
    result = verify_claim(attribute_claim(attribute="clinical_status", attribute_value="active"), ledger)
    assert result.status == "SUPPORTED"


def test_allergy_clinical_status_wrong_contradicted():
    ledger = build_ledger(RICH_PATIENT_ID)
    result = verify_claim(attribute_claim(attribute="clinical_status", attribute_value="resolved"), ledger)
    assert result.status == "CONTRADICTED"


# 4. unknown attribute -> UNVERIFIABLE
def test_unknown_attribute_unverifiable():
    ledger = build_ledger(RICH_PATIENT_ID)
    result = verify_claim(attribute_claim(attribute="severity", attribute_value="severe"), ledger)
    assert result.status == "UNVERIFIABLE"


def test_attribute_claim_for_nonexistent_item_unsupported():
    ledger = build_ledger(RICH_PATIENT_ID)
    result = verify_claim(attribute_claim(value="Latex", attribute="criticality", attribute_value="low"), ledger)
    assert result.status == "UNSUPPORTED"


def test_medication_status_attribute_supported():
    ledger = build_ledger(RICH_PATIENT_ID)
    claim = MedicalClaim(
        text="t", patient_id=RICH_PATIENT_ID, category="medication", value="losartan potassium",
        assertion="attribute", attribute="status", attribute_value="active",
    )
    result = verify_claim(claim, ledger)
    assert result.status == "SUPPORTED"


def test_condition_clinical_status_attribute_supported():
    ledger = build_ledger(RICH_PATIENT_ID)
    claim = MedicalClaim(
        text="t", patient_id=RICH_PATIENT_ID, category="condition", value="Viral sinusitis",
        assertion="attribute", attribute="clinical_status", attribute_value="resolved",
    )
    result = verify_claim(claim, ledger)
    assert result.status == "SUPPORTED"


# 5. attributes preserved in evidence provenance
def test_attributes_preserved_in_provenance():
    ledger = build_ledger(RICH_PATIENT_ID)
    fish_facts = [f for f in ledger.facts_for("allergy") if "Fish" in f.value]
    assert len(fish_facts) == 1
    assert fish_facts[0].attributes == {"criticality": "low", "clinical_status": "active"}

    result = verify_claim(attribute_claim(attribute="criticality", attribute_value="low"), ledger)
    assert len(result.evidence) == 1
    assert result.evidence[0].value == "Fish (substance)"


# 6. old EvidenceFact still loads (attributes defaults to {})
def test_old_evidence_fact_still_loads_without_attributes():
    fact = EvidenceFact(evidence_id="x", patient_id=RICH_PATIENT_ID, category="allergy", value="Fish", source_tool="get_allergies")
    assert fact.attributes == {}


# 7. old MedicalClaim still loads (attribute/attribute_value default to None)
def test_old_medical_claim_still_loads_without_attribute_fields():
    claim = MedicalClaim(text="t", patient_id=RICH_PATIENT_ID, category="allergy", value="Fish", assertion="present")
    assert claim.attribute is None
    assert claim.attribute_value is None


# 8. malformed claim tracked (claim quality, not silently repaired)
def test_malformed_attribute_claim_tracked_as_invalid():
    from meva.ai.agent import _assess_claim_quality

    # assertion="attribute" but missing attribute/attribute_value
    raw = {"text": "t", "patient_id": RICH_PATIENT_ID, "category": "allergy", "value": "Fish", "assertion": "attribute"}
    assert _assess_claim_quality(raw) is False


def test_valid_attribute_claim_tracked_as_valid():
    from meva.ai.agent import _assess_claim_quality

    raw = {
        "text": "t", "patient_id": RICH_PATIENT_ID, "category": "allergy", "value": "Fish",
        "assertion": "attribute", "attribute": "criticality", "attribute_value": "low",
    }
    assert _assess_claim_quality(raw) is True


# 9. wrong category not auto-corrected
def test_wrong_category_claim_not_auto_corrected():
    """If a claim about allergies is mislabeled category='patient', MEVA must NOT guess
    the intended category — it stays a genuine, visible model failure (UNVERIFIABLE)."""
    ledger = build_ledger(RICH_PATIENT_ID)
    mislabeled = MedicalClaim(
        text="No allergies are recorded for this patient.",
        patient_id=RICH_PATIENT_ID, category="patient", value=None, assertion="absent",
    )
    result = verify_claim(mislabeled, ledger)
    # "patient" category doesn't support "absent" assertions at all — MEVA refuses to guess.
    assert result.status == "UNVERIFIABLE"
    assert "does not verify" in result.reason.lower() or "absence" in result.reason.lower()


# --- regression: the Stage 7B allergy example should no longer be unfairly penalized ---

def test_stage_7b_regression_fixed():
    """Fish allergy + criticality low + clinical status active, all stated as separate
    structured claims, should now all be SUPPORTED (previously: 1 supported, 2 unsupported)."""
    claims = [
        MedicalClaim(text="Fish allergy present", patient_id=RICH_PATIENT_ID, category="allergy", value="Fish", assertion="present"),
        MedicalClaim(text="Allergy criticality is low", patient_id=RICH_PATIENT_ID, category="allergy", value="Fish",
                     assertion="attribute", attribute="criticality", attribute_value="low"),
        MedicalClaim(text="Allergy clinical status is active", patient_id=RICH_PATIENT_ID, category="allergy", value="Fish",
                     assertion="attribute", attribute="clinical_status", attribute_value="active"),
    ]
    report = build_report("test", claims)
    assert report.summary.supported == 3
    assert report.summary.unsupported == 0
    assert report.summary.grounding_score == "100%"


def test_parse_agent_answer_extracts_attribute_claims():
    """The agent's structured-output parser should accept and preserve attribute claims."""
    import json
    content = json.dumps({
        "answer": "Fish allergy, criticality low.",
        "claims": [
            {"text": "t", "patient_id": RICH_PATIENT_ID, "category": "allergy", "value": "Fish",
             "assertion": "attribute", "attribute": "criticality", "attribute_value": "low"},
        ],
    })
    agent_answer, quality = _parse_agent_answer(content)
    assert len(agent_answer.claims) == 1
    assert agent_answer.claims[0].attribute == "criticality"
    assert quality["valid_claims"] == 1
    assert quality["structured_claim_validity_rate"] == 1.0
