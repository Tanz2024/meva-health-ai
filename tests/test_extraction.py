"""Stage 7D1 tests: fixed claim extractor, DECOUPLED mode, and metric separation
from END_TO_END. Fully offline — meva.ai.ollama_client.OllamaClient.chat is mocked.
"""

import json
from pathlib import Path
from unittest.mock import patch

from meva.ai.ollama_client import ChatResponse, RunMetrics
from meva.extraction.extractor import extract_claims, run_decoupled_case
from meva.extraction.metrics import decoupled_grounding_metrics, extractor_quality_metrics
from meva.extraction.models import DecoupledCaseResult, ExtractedClaims, EVALUATION_MODES
from meva.verification.models import MedicalClaim

RICH_PATIENT_ID = "080b069b-5108-46b6-ecef-6aacd3b9ef3f"
GOLD_FIXTURES_PATH = Path(__file__).resolve().parent.parent / "data" / "extraction" / "gold_fixtures.json"


def _mock_chat_returning(claims: list[dict], schema_parsed=True):
    if schema_parsed:
        content = json.dumps({"claims": claims})
    else:
        content = "not json at all"
    return ChatResponse(message={"role": "assistant", "content": content}, metrics=RunMetrics(total_duration=1_000_000_000))


# --- 4. existing MedicalClaim schema reused ---------------------------------

def test_extracted_claims_use_existing_medical_claim_schema():
    assert ExtractedClaims.model_fields["claims"].annotation == list[MedicalClaim]


def test_gold_fixtures_expected_claims_parse_as_valid_medical_claims():
    fixtures = json.loads(GOLD_FIXTURES_PATH.read_text())
    assert len(fixtures) >= 10
    for fixture in fixtures:
        for raw_claim in fixture["expected_claims"]:
            MedicalClaim(**raw_claim)  # raises if the schema doesn't match


# --- 5. negative answer preserved as negative claim -------------------------

def test_negative_answer_extracted_as_absent_claim():
    fixtures = {f["id"]: f for f in json.loads(GOLD_FIXTURES_PATH.read_text())}
    fixture = fixtures["negative-allergy"]
    with patch("meva.extraction.extractor.OllamaClient.chat", return_value=_mock_chat_returning(fixture["expected_claims"])):
        result = extract_claims(fixture["question"], fixture["patient_id"], fixture["answer"])
    assert len(result.claims) == 1
    assert result.claims[0].assertion == "absent"
    assert result.claims[0].category == "allergy"


# --- 6. wrong answer is NOT corrected ---------------------------------------

def test_wrong_answer_preserved_not_corrected_by_extractor():
    """The exact Stage 7D1 example: qwen3:4b says 'no blood pressure was found' when
    real evidence has 128/81 — the extractor must preserve the (wrong) claim as stated,
    NOT silently fix it to match reality. Only the downstream verifier may contradict it."""
    wrong_answer = "No blood pressure was found for this patient."
    mocked_extraction = [{
        "text": "No blood pressure found", "patient_id": RICH_PATIENT_ID,
        "category": "observation", "value": "Blood Pressure", "assertion": "absent",
    }]
    with patch("meva.extraction.extractor.OllamaClient.chat", return_value=_mock_chat_returning(mocked_extraction)):
        decoupled = run_decoupled_case(
            case_id="observation-01", category="observation", difficulty="simple", patient_id=RICH_PATIENT_ID,
            source_model="qwen3:4b", question="What is the first recorded blood pressure?",
            answer_text=wrong_answer,
        )
    assert decoupled.extraction_result.claims[0].assertion == "absent"
    assert decoupled.extraction_result.claims[0].value == "Blood Pressure"
    # The real patient (RICH_PATIENT_ID) actually has a recorded BP — MEVA's real,
    # unmodified verifier must catch the extractor's faithfully-preserved wrong claim.
    assert decoupled.contradicted == 1
    assert decoupled.supported == 0


# --- 7. zero factual claims allowed -----------------------------------------

def test_zero_factual_claims_is_a_valid_result():
    fixtures = {f["id"]: f for f in json.loads(GOLD_FIXTURES_PATH.read_text())}
    fixture = fixtures["no-factual-claim"]
    with patch("meva.extraction.extractor.OllamaClient.chat", return_value=_mock_chat_returning([])):
        result = extract_claims(fixture["question"], fixture["patient_id"], fixture["answer"])
    assert result.claims == []
    assert result.schema_parsed is True
    assert result.extraction_error is None


# --- 8. extraction errors isolated ------------------------------------------

def test_extraction_error_isolated_not_raised():
    with patch("meva.extraction.extractor.OllamaClient.chat", side_effect=RuntimeError("connection refused")):
        result = extract_claims("q", RICH_PATIENT_ID, "some answer")
    assert result.schema_parsed is False
    assert "connection refused" in result.extraction_error
    assert result.claims == []


def test_malformed_json_extraction_isolated():
    with patch("meva.extraction.extractor.OllamaClient.chat", return_value=_mock_chat_returning([], schema_parsed=False)):
        result = extract_claims("q", RICH_PATIENT_ID, "some answer")
    assert result.schema_parsed is False
    assert result.extraction_error is not None


# --- 9. END_TO_END and DECOUPLED result modes separated ---------------------

def test_evaluation_modes_are_distinct_and_decoupled_result_is_tagged():
    assert EVALUATION_MODES == ("END_TO_END", "DECOUPLED")
    claims = [{"text": "t", "patient_id": RICH_PATIENT_ID, "category": "allergy", "value": "Fish", "assertion": "present"}]
    with patch("meva.extraction.extractor.OllamaClient.chat", return_value=_mock_chat_returning(claims)):
        decoupled = run_decoupled_case(
            case_id="allergy-01", category="allergy", difficulty="simple", patient_id=RICH_PATIENT_ID,
            source_model="qwen3:4b", question="q", answer_text="Fish allergy recorded.",
        )
    assert decoupled.mode == "DECOUPLED"
    assert isinstance(decoupled, DecoupledCaseResult)


# --- 10-12. original answer / source_model / extractor_model preserved -----

def test_original_answer_and_models_preserved_for_audit():
    with patch("meva.extraction.extractor.OllamaClient.chat", return_value=_mock_chat_returning([])):
        decoupled = run_decoupled_case(
            case_id="c1", category="allergy", difficulty="simple", patient_id=RICH_PATIENT_ID,
            source_model="llama3.2:3b", question="Original question text", answer_text="Original answer text.",
            extractor_model="qwen3:4b",
        )
    assert decoupled.source_model == "llama3.2:3b"
    assert decoupled.original_question == "Original question text"
    assert decoupled.original_natural_language_answer == "Original answer text."
    assert decoupled.extractor_model == "qwen3:4b"


# --- 13. decoupled verifier uses the existing deterministic verifier -------

def test_decoupled_uses_existing_verifier_and_real_evidence():
    claims = [{"text": "t", "patient_id": RICH_PATIENT_ID, "category": "allergy", "value": "Fish (substance)", "assertion": "present"}]
    with patch("meva.extraction.extractor.OllamaClient.chat", return_value=_mock_chat_returning(claims)):
        decoupled = run_decoupled_case(
            case_id="allergy-01", category="allergy", difficulty="simple", patient_id=RICH_PATIENT_ID,
            source_model="qwen3:4b", question="q", answer_text="Fish allergy recorded.",
        )
    # RICH_PATIENT_ID genuinely has a Fish allergy in the real synthetic FHIR bundle —
    # this proves build_report() actually looked up real evidence, not a stub.
    assert decoupled.supported == 1
    assert decoupled.evidence_grounding_score == "100%"


# --- 14. metrics don't mix end-to-end and decoupled -------------------------

def test_extractor_quality_metrics_never_labeled_as_answer_quality():
    from meva.extraction.models import ExtractionResult
    results = [
        ExtractionResult(answer_text="a", claims=[], total_raw_claims=0, schema_parsed=True, model="qwen3:4b"),
        ExtractionResult(answer_text="b", claims=[MedicalClaim(text="t", patient_id=RICH_PATIENT_ID, category="allergy", value="Fish", assertion="present")],
                          total_raw_claims=1, schema_parsed=True, model="qwen3:4b"),
    ]
    metrics = extractor_quality_metrics(results)
    assert set(metrics) == {
        "extractor_schema_success_rate", "extracted_claim_validity_rate",
        "zero_extracted_claim_rate", "extraction_error_rate", "total_extracted_claims",
    }
    assert "answer_quality" not in metrics
    assert metrics["zero_extracted_claim_rate"] == 0.5


def test_decoupled_grounding_metrics_are_separately_labeled():
    with patch("meva.extraction.extractor.OllamaClient.chat", return_value=_mock_chat_returning(
        [{"text": "t", "patient_id": RICH_PATIENT_ID, "category": "allergy", "value": "Fish (substance)", "assertion": "present"}]
    )):
        decoupled = run_decoupled_case(
            case_id="allergy-01", category="allergy", difficulty="simple", patient_id=RICH_PATIENT_ID,
            source_model="qwen3:4b", question="q", answer_text="Fish allergy recorded.",
        )
    metrics = decoupled_grounding_metrics([decoupled])
    assert metrics["mode"] == "DECOUPLED"
    assert "structured_claim_validity_rate" not in metrics  # that's an END_TO_END-only concept
