"""Data structures for MEVA's benchmark engine.

A BenchmarkCase describes one question to ask MEVA, and what a correct
run should look like. A BenchmarkResult is what actually happened when
MEVA ran that case. Neither model contains any AI logic — see
graph.py/runner.py for the actual execution.
"""

from pydantic import BaseModel, Field

from meva.verification.models import MedicalClaim

BENCHMARK_CATEGORIES = (
    "allergy",
    "medication",
    "condition",
    "observation",
    "patient",
    "empty_evidence",
    "invalid_patient",
    "contradiction",
    "multi_tool",
    "verifier_challenge",
)

# Case statuses a BenchmarkResult can end in.
RESULT_STATUSES = ("passed", "failed", "error")

# AGENT: runs the normal local-model pipeline (Stage 7A behavior).
# VERIFIER_CHALLENGE: feeds a deliberately wrong/tricky claim straight into
# MEVA's verifier, bypassing the live model. This tests MEVA's verification
# logic itself, not the local model — its results must never be reported
# as evidence of model (e.g. Qwen) performance. See docs/benchmarking.md.
CASE_TYPES = ("AGENT", "VERIFIER_CHALLENGE")

# Engineering complexity label — NOT a medical/clinical difficulty judgement.
# - simple: one tool, one expected fact
# - multi_fact: one tool, 2+ expected facts (e.g. a name plus its attributes)
# - multi_tool: 2+ tools required
# - negative: an absence/empty-evidence case
# - error: an invalid-patient / error-handling case
DIFFICULTIES = ("simple", "multi_fact", "multi_tool", "negative", "error")


class ExpectedEvidence(BaseModel):
    """One structured fact a case expects to find in the real FHIR bundle.

    Every field here should be filled in by reading the actual Synthea
    bundle (see examples/inspect_benchmark_data.py) — never guessed.
    """

    category: str
    value: str
    source_tool: str
    resource_id: str | None = None


class BenchmarkCase(BaseModel):
    """One benchmark question and what a correct run of it should look like."""

    case_id: str
    category: str
    patient_id: str
    question: str
    expected_tools: list[str] = Field(default_factory=list)
    description: str
    expected_status: str | None = None  # SUPPORTED / CONTRADICTED / UNSUPPORTED / UNVERIFIABLE, when known
    case_type: str = "AGENT"
    difficulty: str | None = None  # one of DIFFICULTIES; an engineering complexity label, not a medical one

    # v0.1-style loose evidence strings (kept for backward compatibility).
    expected_evidence: list[str] = Field(default_factory=list)
    # v0.2-style structured evidence facts, each traceable to a specific FHIR resource.
    expected_evidence_facts: list[ExpectedEvidence] = Field(default_factory=list)

    # Only used by VERIFIER_CHALLENGE cases (or the legacy category=="contradiction"
    # cases from v0.1): a deliberately wrong claim fed straight into verification,
    # bypassing the live model. See docs/benchmarking.md for why "does the model lie
    # convincingly" isn't a fair or reproducible thing to test with a live model.
    injected_claim: dict | None = None


class BenchmarkResult(BaseModel):
    """What actually happened when MEVA ran one BenchmarkCase."""

    case_id: str
    category: str
    case_type: str = "AGENT"
    difficulty: str | None = None
    patient_id: str
    question: str

    tool_calls: list[str] = Field(default_factory=list)
    expected_tools: list[str] = Field(default_factory=list)

    # Legacy Stage 7A metric: True iff expected_tools is a subset of the tools called.
    # Kept for backward compatibility; superseded by the metrics below (see
    # docs/benchmarking.md, "Tool metrics").
    tool_selection_correct: bool | None = None

    # Stage 7B tool metrics (see metrics.py for exact formulas).
    unique_tool_calls: int = 0
    total_tool_calls: int = 0
    duplicate_tool_calls: int = 0
    required_tool_recall: float | None = None
    tool_precision: float | None = None
    exact_tool_match: bool | None = None
    tool_overcall_count: int = 0

    evidence_recall: float | None = None  # None = unavailable (no expected_evidence_facts to check)
    structured_claim_validity_rate: float | None = None  # None = not applicable (VERIFIER_CHALLENGE, error, or zero claims)

    # Stage 7C2: how much of the model's raw claim output MEVA could even attempt to verify.
    total_emitted_claims: int = 0
    zero_claim: bool = False  # model produced an answer but zero structured claims (still a structured-output failure)
    verifiable_claim_coverage: float | None = None  # (supported+contradicted+unsupported) / total_emitted_claims
    malformed_attribute_claim_count: int = 0
    wrong_category_or_assertion_count: int = 0

    answer: str | None = None
    claims: list[MedicalClaim] = Field(default_factory=list)

    supported: int = 0
    contradicted: int = 0
    unsupported: int = 0
    unverifiable: int = 0
    evidence_grounding_score: str = "N/A"

    # Stage 7C2: non-exclusive case-outcome flags — a case can carry more than one.
    # AGENT cases only; always False for VERIFIER_CHALLENGE/error results.
    retrieval_failure: bool = False
    structured_output_failure: bool = False
    grounding_failure: bool = False
    successful: bool = False

    expected_status: str | None = None
    expected_status_achieved: bool | None = None

    tool_call_latency_seconds: float | None = None
    structured_latency_seconds: float | None = None
    total_latency_seconds: float | None = None

    status: str = "error"  # "passed" | "failed" | "error"
    error_type: str | None = None
    error_message: str | None = None
