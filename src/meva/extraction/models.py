"""Data structures for MEVA's decoupled claim-extraction evaluation (Stage 7D1).

No verification logic lives here — extraction produces MedicalClaims (the
same schema MEVA's agent already uses); meva.verification does the actual
checking, unchanged. See meva.extraction.extractor for the anti-leakage
rules that make this a fair, separate measurement from END_TO_END mode.
"""

from pydantic import BaseModel, Field

from meva.verification.models import MedicalClaim

# The two official evaluation modes (Stage 7D1) — never silently combined
# or averaged together. See docs/decoupled-evaluation.md.
EVALUATION_MODES = ("END_TO_END", "DECOUPLED")


class ExtractedClaims(BaseModel):
    """The extractor's raw structured-output shape — just a list of claims.

    Deliberately smaller than AgentAnswer (meva.verification.models): the
    extractor is not asked to restate the answer, only to represent the
    factual claims already in it.
    """

    claims: list[MedicalClaim] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    """What happened when the fixed extractor processed one saved natural-language answer.

    `metrics` is the raw {"total_duration": ..., ...} dict from Ollama (see
    meva.ai.ollama_client.RunMetrics), kept as a plain dict here to avoid a
    circular import — never invented, always Ollama's own reported numbers.
    """

    answer_text: str
    claims: list[MedicalClaim] = Field(default_factory=list)  # only claims that passed validity checks
    total_raw_claims: int = 0  # every claim object the extractor emitted, valid or not
    schema_parsed: bool
    extraction_error: str | None = None
    model: str
    metrics: dict | None = None


class DecoupledCaseResult(BaseModel):
    """One full decoupled-mode result: a saved model answer, run through the
    fixed extractor and MEVA's existing deterministic verifier.

    Every field needed to audit "what did the source model actually say,
    what did the extractor turn it into, what did the verifier decide" is
    kept together and explicit — see docs/decoupled-evaluation.md.
    """

    mode: str = "DECOUPLED"

    case_id: str
    category: str
    difficulty: str | None = None
    patient_id: str

    source_model: str
    original_question: str
    original_natural_language_answer: str

    extractor_model: str
    extraction_result: ExtractionResult

    verification_report: dict  # meva.verification.models.VerificationReport.model_dump()

    supported: int = 0
    contradicted: int = 0
    unsupported: int = 0
    unverifiable: int = 0
    evidence_grounding_score: str = "N/A"
    verifiable_claim_coverage: float | None = None
    total_emitted_claims: int = 0
