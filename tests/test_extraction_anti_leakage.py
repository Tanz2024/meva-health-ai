"""Stage 7D1 anti-leakage tests: the fixed claim extractor must never receive
FHIR evidence, expected benchmark evidence, the expected verification result,
or the source model's own original structured claims — only question,
patient_id, and the natural-language answer text. Fully offline.
"""

import inspect

from meva.extraction.extractor import ALLOWED_EXTRACTOR_INPUT_FIELDS, extract_claims
from meva.extraction.prompt import build_extraction_messages

FORBIDDEN_KEYWORDS = (
    "fhir", "evidencefact", "expected_evidence", "expected_status", "mcp", "tool_result",
    "resourcetype", "bundle", "original_claims", "structured_claims",
)


def test_extractor_function_signature_has_no_evidence_parameters():
    sig = inspect.signature(extract_claims)
    param_names = set(sig.parameters)
    forbidden_params = {"fhir_bundle", "evidence", "expected_evidence", "expected_status", "tool_results", "claims", "original_claims"}
    assert not (param_names & forbidden_params)


def test_only_allowed_fields_are_extractor_input():
    assert ALLOWED_EXTRACTOR_INPUT_FIELDS == ("question", "patient_id", "answer_text")


def test_extraction_messages_contain_no_fhir_or_evidence_data():
    messages = build_extraction_messages(
        question="What allergies are recorded for patient p1?",
        patient_id="p1",
        answer_text="No allergies were found.",
    )
    full_text = " ".join(m["content"] for m in messages).lower()
    for keyword in FORBIDDEN_KEYWORDS:
        assert keyword not in full_text, f"extraction prompt leaked forbidden term: {keyword}"


def test_extraction_messages_contain_only_question_patient_id_and_answer():
    question = "UNIQUE_QUESTION_MARKER_123"
    patient_id = "UNIQUE_PATIENT_MARKER_456"
    answer_text = "UNIQUE_ANSWER_MARKER_789"
    messages = build_extraction_messages(question, patient_id, answer_text)
    user_message = messages[-1]["content"]

    assert question in user_message
    assert patient_id in user_message
    assert answer_text in user_message
    # The system prompt (a fixed, static string with no case data) is the only other content.
    assert "UNIQUE" in user_message  # sanity: markers actually landed somewhere


def test_extraction_prompt_never_mentions_expected_evidence_or_expected_status():
    messages = build_extraction_messages("q", "p1", "No blood pressure observation was found.")
    for m in messages:
        assert "expected_evidence" not in m["content"].lower()
        assert "expected_status" not in m["content"].lower()
