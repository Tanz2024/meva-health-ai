"""The fixed local claim extractor (Stage 7D1).

Turns an already-produced natural-language answer into structured
MedicalClaims — without ever seeing the FHIR evidence, the benchmark's
expected evidence, the expected verification result, or the source
model's own original structured claims. Only the question, patient_id,
and answer text go in. See docs/decoupled-evaluation.md for why this
matters: if the extractor could see the evidence, it could "fix" a wrong
answer by adding correct information the source model never actually said.

This is model-assisted extraction, not deterministic parsing — running it
twice on the same input is not guaranteed to produce byte-identical output,
even with temperature=0/seed=42 (a local model's exact reproducibility
across runs isn't guaranteed by MEVA, only that the same settings are used
every time — see docs/reproducibility.md). The verification step downstream
of extraction remains fully deterministic Python, unchanged.
"""

import json

from pydantic import ValidationError

from meva.ai.ollama_client import OllamaClient
from meva.extraction.metrics import verifiable_claim_coverage
from meva.extraction.models import DecoupledCaseResult, ExtractedClaims, ExtractionResult
from meva.extraction.prompt import build_extraction_messages
from meva.verification.models import CLAIM_CATEGORIES, MedicalClaim
from meva.verification.verifier import build_report

# The ONLY fields extract_claims() accepts as case data — question, patient_id,
# and answer_text. No FHIR bundle, no EvidenceFact/expected-evidence, no expected
# verification result, no original model-generated structured claims. Tests in
# tests/test_extraction_anti_leakage.py assert this stays true.
ALLOWED_EXTRACTOR_INPUT_FIELDS = ("question", "patient_id", "answer_text")

EXTRACTION_TEMPERATURE = 0
EXTRACTION_SEED = 42
EXTRACTION_THINK = False
EXTRACTION_KEEP_ALIVE = "5m"


def _claim_is_valid(claim: MedicalClaim) -> bool:
    if claim.category not in CLAIM_CATEGORIES:
        return False
    if claim.assertion in ("present", "value", "attribute") and not claim.value:
        return False
    if claim.assertion == "attribute" and not (claim.attribute and claim.attribute_value):
        return False
    return True


def extract_claims(
    question: str,
    patient_id: str,
    answer_text: str,
    model: str | None = None,
    base_url: str | None = None,
    temperature: float = EXTRACTION_TEMPERATURE,
    seed: int = EXTRACTION_SEED,
    think: bool = EXTRACTION_THINK,
    keep_alive: str = EXTRACTION_KEEP_ALIVE,
) -> ExtractionResult:
    """Run the fixed extractor over one saved answer. Local Ollama only.

    Accepts ONLY question/patient_id/answer_text as case data (see
    ALLOWED_EXTRACTOR_INPUT_FIELDS) — there is deliberately no parameter
    for FHIR data, expected evidence, or the source model's own claims.
    """
    messages = build_extraction_messages(question, patient_id, answer_text)
    client = OllamaClient(base_url=base_url, model=model)
    schema = ExtractedClaims.model_json_schema()

    try:
        response = client.chat(
            messages, tools=None, format=schema,
            think=think, temperature=temperature, seed=seed, keep_alive=keep_alive,
        )
    except Exception as e:
        return ExtractionResult(
            answer_text=answer_text, claims=[], schema_parsed=False,
            extraction_error=f"{type(e).__name__}: {e}", model=client.model, metrics=None,
        )

    content = response.message.get("content", "")
    metrics = response.metrics.model_dump()

    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return ExtractionResult(
            answer_text=answer_text, claims=[], schema_parsed=False,
            extraction_error="Extractor output was not valid JSON.", model=client.model, metrics=metrics,
        )

    if not isinstance(data, dict) or "claims" not in data:
        return ExtractionResult(
            answer_text=answer_text, claims=[], schema_parsed=False,
            extraction_error="Extractor output did not match the expected {'claims': [...]} shape.",
            model=client.model, metrics=metrics,
        )

    raw_claims = data.get("claims") or []
    claims = []
    for raw_claim in raw_claims:
        try:
            claim = MedicalClaim(**raw_claim)
        except (TypeError, ValidationError):
            continue
        if _claim_is_valid(claim):
            claims.append(claim)

    return ExtractionResult(
        answer_text=answer_text, claims=claims, total_raw_claims=len(raw_claims), schema_parsed=True,
        extraction_error=None, model=client.model, metrics=metrics,
    )


def run_decoupled_case(
    case_id: str,
    category: str,
    difficulty: str | None,
    patient_id: str,
    source_model: str,
    question: str,
    answer_text: str,
    extractor_model: str | None = None,
    base_url: str | None = None,
) -> DecoupledCaseResult:
    """DECOUPLED mode, end to end: a saved (source_model, answer_text) pair -> extraction ->
    MEVA's existing deterministic verifier (meva.verification.verifier.build_report, unchanged).

    Ignores whatever structured claims the source model originally produced — extraction is
    the ONLY source of claims here (see docs/decoupled-evaluation.md, "why the two modes
    answer different questions").
    """
    extraction = extract_claims(question, patient_id, answer_text, model=extractor_model, base_url=base_url)
    report = build_report(answer_text, extraction.claims)
    summary = report.summary

    total_emitted = extraction.total_raw_claims
    coverage = verifiable_claim_coverage(summary.supported, summary.contradicted, summary.unsupported, total_emitted)

    return DecoupledCaseResult(
        case_id=case_id, category=category, difficulty=difficulty, patient_id=patient_id,
        source_model=source_model, original_question=question, original_natural_language_answer=answer_text,
        extractor_model=extraction.model, extraction_result=extraction,
        verification_report=report.model_dump(),
        supported=summary.supported, contradicted=summary.contradicted,
        unsupported=summary.unsupported, unverifiable=summary.unverifiable,
        evidence_grounding_score=summary.grounding_score,
        verifiable_claim_coverage=coverage, total_emitted_claims=total_emitted,
    )
