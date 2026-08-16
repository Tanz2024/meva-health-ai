"""Aggregate metrics for the fixed claim extractor and for DECOUPLED-mode results.

These describe the EXTRACTOR's behavior (extractor_schema_success_rate,
extracted_claim_validity_rate, ...) or the DECOUPLED verification outcome
(grounding, coverage) — never the tested (source) model's own answer
quality. See docs/decoupled-evaluation.md: END_TO_END and DECOUPLED numbers
are never combined or averaged together, and this module never produces a
number that mixes the two.
"""

import statistics

from meva.extraction.models import DecoupledCaseResult, ExtractionResult


def _mean_or_none(values: list[float]) -> float | None:
    return statistics.mean(values) if values else None


def _grounding_score(supported: int, contradicted: int, unsupported: int) -> str:
    verifiable = supported + contradicted + unsupported
    return f"{round(100 * supported / verifiable)}%" if verifiable else "N/A"


def verifiable_claim_coverage(supported: int, contradicted: int, unsupported: int, total_emitted_claims: int) -> float | None:
    """Same micro-average-of-totals formula as meva.benchmark.metrics.verifiable_claim_coverage
    (duplicated here, not imported, to keep meva.extraction free of a meva.benchmark dependency)."""
    if total_emitted_claims == 0:
        return None
    return (supported + contradicted + unsupported) / total_emitted_claims


def extractor_quality_metrics(results: list[ExtractionResult]) -> dict:
    """Metrics describing the FIXED EXTRACTOR's own behavior — not the source model's."""
    n = len(results)
    if n == 0:
        return {
            "extractor_schema_success_rate": None, "extracted_claim_validity_rate": None,
            "zero_extracted_claim_rate": None, "extraction_error_rate": None, "total_extracted_claims": 0,
        }

    schema_successes = sum(1 for r in results if r.schema_parsed)
    errors = sum(1 for r in results if r.extraction_error is not None)
    zero_claim_cases = sum(1 for r in results if r.schema_parsed and r.total_raw_claims == 0)

    validity_rates = []
    for r in results:
        if not r.schema_parsed or r.total_raw_claims == 0:
            continue
        validity_rates.append(len(r.claims) / r.total_raw_claims)

    return {
        "extractor_schema_success_rate": schema_successes / n,
        "extracted_claim_validity_rate": _mean_or_none(validity_rates),
        "zero_extracted_claim_rate": zero_claim_cases / n,
        "extraction_error_rate": errors / n,
        "total_extracted_claims": sum(len(r.claims) for r in results),
    }


def case_outcome(supported: int, contradicted: int, unsupported: int, unverifiable: int) -> str:
    """A single deterministic label for one case's claim verdicts, most-severe-first —
    used only to compare END_TO_END vs DECOUPLED at the case level (Stage 7D2), never
    to replace the underlying per-claim SUPPORTED/CONTRADICTED/UNSUPPORTED/UNVERIFIABLE counts."""
    if contradicted > 0:
        return "CONTRADICTED"
    if unsupported > 0:
        return "UNSUPPORTED"
    if supported > 0:
        return "SUPPORTED"
    if unverifiable > 0:
        return "UNVERIFIABLE"
    return "NONE"


def classify_disagreement_cause(end_to_end_case, decoupled_case: DecoupledCaseResult) -> str:
    """Deterministic (no LLM judge) best-effort explanation for why END_TO_END and DECOUPLED
    reached a different case_outcome for the same case. `end_to_end_case` is a
    meva.benchmark.models.BenchmarkResult (duck-typed here to avoid a meva.benchmark
    dependency in meva.extraction)."""
    if getattr(end_to_end_case, "zero_claim", False):
        return "zero original claims"
    validity = getattr(end_to_end_case, "structured_claim_validity_rate", None)
    if validity is not None and validity < 1.0:
        return "original structured-claim failure"
    if len(decoupled_case.extraction_result.claims) != len(end_to_end_case.claims):
        return "extraction difference"
    return "other"


def find_method_disagreements(end_to_end_results: list, decoupled_results: list[DecoupledCaseResult]) -> list[dict]:
    """Cases where END_TO_END's case_outcome differs from DECOUPLED's, with a deterministic cause."""
    decoupled_by_case = {r.case_id: r for r in decoupled_results}
    disagreements = []
    for e2e in end_to_end_results:
        decoupled = decoupled_by_case.get(e2e.case_id)
        if decoupled is None:
            continue
        e2e_outcome = case_outcome(e2e.supported, e2e.contradicted, e2e.unsupported, e2e.unverifiable)
        dec_outcome = case_outcome(decoupled.supported, decoupled.contradicted, decoupled.unsupported, decoupled.unverifiable)
        if e2e_outcome != dec_outcome:
            disagreements.append({
                "case_id": e2e.case_id,
                "end_to_end_outcome": e2e_outcome,
                "decoupled_outcome": dec_outcome,
                "cause": classify_disagreement_cause(e2e, decoupled),
            })
    return disagreements


def find_grounding_failure_preservation(end_to_end_results: list, decoupled_results: list[DecoupledCaseResult]) -> list[dict]:
    """Cases where BOTH END_TO_END and DECOUPLED independently found a CONTRADICTED claim —
    proof decoupling doesn't automatically erase a genuine answer error (e.g. the qwen3:4b
    blood-pressure hallucination, Stage 7D1)."""
    decoupled_by_case = {r.case_id: r for r in decoupled_results}
    preserved = []
    for e2e in end_to_end_results:
        decoupled = decoupled_by_case.get(e2e.case_id)
        if decoupled is None:
            continue
        if e2e.contradicted > 0 and decoupled.contradicted > 0:
            preserved.append({
                "case_id": e2e.case_id,
                "end_to_end_contradicted": e2e.contradicted,
                "decoupled_contradicted": decoupled.contradicted,
            })
    return preserved


def claim_recovery(end_to_end_results: list, decoupled_results: list[DecoupledCaseResult]) -> dict:
    """Cases where END_TO_END emitted zero or entirely-invalid/unverifiable structured claims,
    but DECOUPLED extraction produced at least one valid claim from the same saved prose.

    Describes evaluation-METHOD recovery, not the source model "improving" — see
    docs/decoupled-evaluation.md.
    """
    decoupled_by_case = {r.case_id: r for r in decoupled_results}
    recovered_case_ids = []
    for e2e in end_to_end_results:
        decoupled = decoupled_by_case.get(e2e.case_id)
        if decoupled is None:
            continue
        e2e_had_no_usable_claims = (
            e2e.zero_claim
            or (e2e.structured_claim_validity_rate is not None and e2e.structured_claim_validity_rate < 1.0)
        )
        if e2e_had_no_usable_claims and len(decoupled.extraction_result.claims) > 0:
            recovered_case_ids.append(e2e.case_id)

    total = len(end_to_end_results)
    return {
        "claim_recovery_count": len(recovered_case_ids),
        "claim_recovery_case_rate": (len(recovered_case_ids) / total) if total else None,
        "recovered_case_ids": recovered_case_ids,
    }


def group_decoupled_metrics(results: list[DecoupledCaseResult], key_fn) -> dict:
    """Group DECOUPLED results by an arbitrary key (category/difficulty), each with its own n."""
    groups: dict[str, list[DecoupledCaseResult]] = {}
    for r in results:
        key = key_fn(r) or "unlabeled"
        groups.setdefault(key, []).append(r)
    return {key: {"n": len(rs), **decoupled_grounding_metrics(rs)} for key, rs in groups.items()}


def decoupled_grounding_metrics(results: list[DecoupledCaseResult]) -> dict:
    """DECOUPLED-mode grounding/coverage metrics — the exact same verifier and formulas
    as END_TO_END mode, just run over extracted (not model-self-generated) claims."""
    n = len(results)
    supported = sum(r.supported for r in results)
    contradicted = sum(r.contradicted for r in results)
    unsupported = sum(r.unsupported for r in results)
    unverifiable = sum(r.unverifiable for r in results)
    total_emitted = sum(r.total_emitted_claims for r in results)
    verifiable = supported + contradicted + unsupported

    return {
        "mode": "DECOUPLED",
        "cases": n,
        "supported_claims": supported,
        "contradicted_claims": contradicted,
        "unsupported_claims": unsupported,
        "unverifiable_claims": unverifiable,
        "verifiable_claims": verifiable,
        "total_emitted_claims": total_emitted,
        "evidence_grounding_score": _grounding_score(supported, contradicted, unsupported),
        "verifiable_claim_coverage": verifiable_claim_coverage(supported, contradicted, unsupported, total_emitted),
    }
