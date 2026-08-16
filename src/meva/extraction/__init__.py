"""MEVA's decoupled claim-extraction evaluation (Stage 7D1).

END_TO_END benchmarking (meva.benchmark) asks a tested model to both answer
a question AND encode its own answer into MEVA's structured claim schema.
DECOUPLED mode separates those two jobs: a saved natural-language answer is
handed to a FIXED extractor model, and only the extractor's claims are
verified. This isolates "did the model say the right thing" from "did the
model correctly format what it said" — see docs/decoupled-evaluation.md.

This package contains no FHIR parsing and no verification rules of its
own — extraction produces the same MedicalClaim objects meva.verification
already knows how to check, and meva.verification.verifier.build_report is
used unchanged.
"""

from meva.extraction.extractor import extract_claims, run_decoupled_case
from meva.extraction.fidelity import (
    aggregate_error_counts,
    aggregate_fidelity_metrics,
    claim_key,
    classify_mismatches,
    evaluate_fixture,
    evaluate_gold_fixtures,
    match_claims,
    passes_decision_gate,
    passes_holdout_gate,
)
from meva.extraction.metrics import (
    case_outcome,
    claim_recovery,
    decoupled_grounding_metrics,
    extractor_quality_metrics,
    find_grounding_failure_preservation,
    find_method_disagreements,
    group_decoupled_metrics,
)
from meva.extraction.models import DecoupledCaseResult, EVALUATION_MODES, ExtractedClaims, ExtractionResult

__all__ = [
    "extract_claims",
    "run_decoupled_case",
    "extractor_quality_metrics",
    "decoupled_grounding_metrics",
    "DecoupledCaseResult",
    "ExtractionResult",
    "ExtractedClaims",
    "EVALUATION_MODES",
    "claim_key",
    "match_claims",
    "evaluate_fixture",
    "evaluate_gold_fixtures",
    "aggregate_fidelity_metrics",
    "passes_decision_gate",
    "passes_holdout_gate",
    "classify_mismatches",
    "aggregate_error_counts",
    "case_outcome",
    "claim_recovery",
    "find_grounding_failure_preservation",
    "find_method_disagreements",
    "group_decoupled_metrics",
]
