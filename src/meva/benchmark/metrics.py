"""Latency, tool-selection, and evidence-recall metrics for MEVA's benchmark.

Every number here comes from real, reported values (Ollama's own
metrics, MEVA's own verification counts, or an actual tool-call log) —
never invented. Missing/uncheckable data becomes None ("N/A" when
displayed), not a fabricated zero.

Tool metrics (per AGENT case), given expected_tools E and the actual
list of tool names called T (as a multiset — duplicates matter for
duplicate-call tracking, but tool sets below use unique names):

    unique_tool_calls     = |unique(T)|
    total_tool_calls      = |T|
    duplicate_tool_calls  = total_tool_calls - unique_tool_calls

    matched = |E ∩ unique(T)|
    required_tool_recall  = matched / |E|            (None if E is empty)
    tool_precision        = matched / |unique(T)|     (None if no tools were called)
    exact_tool_match      = (unique(T) == E)          (as sets)
    tool_overcall_count   = |unique(T) - E|

Evidence recall (per case, only when expected_evidence_facts is non-empty):

    evidence_recall = (expected facts found in the actual tool results) / (total expected facts)

Matching uses MEVA's existing conservative normalizer (meva.verification.normalizer) —
no fuzzy/semantic matching is introduced here.

Raw vs. parsed vs. verifiable claim counts (Stage 7C2 / 7C2.1), per case and aggregated:

    raw_emitted_claims = total_emitted_claims
        Every claim object the model's structured JSON output contained, valid
        or not — before MEVA drops anything malformed (see meva.ai.agent._parse_agent_answer).

    parsed_claims
        raw_emitted_claims that passed schema parsing and were handed to the verifier
        (== len(claims) on a BenchmarkResult). Malformed claims are dropped here, never
        silently repaired.

    verifiable_claims = supported + contradicted + unsupported
        Parsed claims MEVA's verifier reached an actual SUPPORTED/CONTRADICTED/UNSUPPORTED
        verdict on. Excludes UNVERIFIABLE (a real, counted verdict, just not usable as a
        numerator/denominator input for "was this claim right").

Aggregate formulas that use these (see _agent_metrics_summary — the SAME formula is applied
whether computed over the whole run or one grouped subset, e.g. one category):

    verifiable_claim_coverage = verifiable_claims / raw_emitted_claims   (aggregate, i.e. a
        MICRO-average over the group's TOTALS — not a mean of each case's own coverage ratio;
        None if raw_emitted_claims is 0). This is the metric documented in
        docs/model-comparison.md — "how much of the model's emitted claim output could MEVA
        verify at all." A per-case macro-average would silently exclude zero-claim cases from
        the denominator instead of counting them as 0% coverage, understating how often a
        model fails to emit anything checkable — this was a real Stage 7C2 bug, fixed in
        Stage 7C2.1 (see mean_case_verifiable_coverage below for what NOT to use here).

    mean_case_verifiable_coverage = mean(each case's own coverage), among cases that emitted
        at least one claim. Kept only under this distinct, explicit name — never reported as
        verifiable_claim_coverage. Two different formulas must never share one metric name.

    evidence_grounding_score = supported / verifiable_claims   ("N/A" if verifiable_claims is 0)
        Of claims MEVA COULD verify, how many were supported? Different question than
        verifiable_claim_coverage — never combined into one score.
"""

import statistics

from meva.benchmark.models import BenchmarkCase, BenchmarkResult, ExpectedEvidence
from meva.verification.normalizer import values_match


def _seconds(metrics_list: list[dict]) -> float | None:
    """Sum total_duration (nanoseconds) across a list of metric dicts, in seconds."""
    if not metrics_list:
        return None
    totals = [m.get("total_duration") for m in metrics_list]
    if any(t is None for t in totals):
        return None
    return sum(totals) / 1e9


def extract_latencies(metrics: dict | None) -> dict:
    """Turn one case's raw {"tool_calls": [...], "final": {...}|None} metrics into seconds."""
    metrics = metrics or {}
    tool_call_seconds = _seconds(metrics.get("tool_calls") or [])
    final_metric = metrics.get("final")
    structured_seconds = _seconds([final_metric]) if final_metric else None

    total_seconds = None
    if tool_call_seconds is not None and structured_seconds is not None:
        total_seconds = tool_call_seconds + structured_seconds
    elif tool_call_seconds is not None:
        total_seconds = tool_call_seconds
    elif structured_seconds is not None:
        total_seconds = structured_seconds

    return {
        "tool_call_seconds": tool_call_seconds,
        "structured_seconds": structured_seconds,
        "total_seconds": total_seconds,
    }


def tool_metrics(expected_tools: list[str], tool_calls: list[str]) -> dict:
    """Compute the Stage 7B tool-selection metrics for one case. See module docstring for formulas."""
    expected = set(expected_tools)
    unique_calls = set(tool_calls)

    matched = len(expected & unique_calls)
    unique_tool_calls = len(unique_calls)
    total_tool_calls = len(tool_calls)

    return {
        "unique_tool_calls": unique_tool_calls,
        "total_tool_calls": total_tool_calls,
        "duplicate_tool_calls": total_tool_calls - unique_tool_calls,
        "required_tool_recall": (matched / len(expected)) if expected else None,
        "tool_precision": (matched / unique_tool_calls) if unique_tool_calls else None,
        "exact_tool_match": unique_calls == expected,
        "tool_overcall_count": len(unique_calls - expected),
    }


def _candidate_values(tool: str, result) -> list[str]:
    """Pull comparable string values out of one tool-call's raw result, for evidence matching."""
    values = []

    if isinstance(result, dict):
        # e.g. get_patient's single-record result
        for value in result.values():
            if isinstance(value, str):
                values.append(value)
        return values

    if isinstance(result, list):
        for item in result:
            if not isinstance(item, dict):
                continue
            if item.get("name"):
                values.append(item["name"])
            if item.get("value"):
                values.append(f"{item['name']}: {item['value']}" if item.get("name") else item["value"])
            if item.get("blood_pressure"):
                values.append(f"{item.get('name', 'Blood Pressure')}: {item['blood_pressure']}")
            if item.get("type"):
                values.append(str(item["type"]))
            if item.get("status") and tool != "get_medications":
                values.append(str(item["status"]))

    return values


def evidence_recall(expected_facts: list[ExpectedEvidence], log: list[dict]) -> float | None:
    """Fraction of expected_facts actually found in the case's real tool-call log.

    Returns None ("unavailable") when there are no expected facts to check —
    never a fabricated 0.0 or 1.0.
    """
    if not expected_facts:
        return None

    found = 0
    for fact in expected_facts:
        candidates = []
        for entry in log:
            if entry.get("tool") != fact.source_tool:
                continue
            candidates.extend(_candidate_values(entry["tool"], entry.get("result")))

        if any(values_match(fact.value, candidate) for candidate in candidates):
            found += 1

    return found / len(expected_facts)


def _median_or_none(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _mean_or_none(values: list[float]) -> float | None:
    return statistics.mean(values) if values else None


def _grounding_score(supported: int, contradicted: int, unsupported: int) -> str:
    verifiable = supported + contradicted + unsupported
    return f"{round(100 * supported / verifiable)}%" if verifiable else "N/A"


def verifiable_claim_coverage(supported: int, contradicted: int, unsupported: int, total_emitted_claims: int) -> float | None:
    """How much of the model's emitted claim output MEVA could even attempt to verify.

    This answers a different question than Evidence Grounding Score:
    - Evidence Grounding Score: of claims MEVA COULD verify, how many were supported?
    - Verifiable Claim Coverage: how much of the model's OUTPUT could MEVA verify at all?

    UNVERIFIABLE claims reduce this number (they're emitted but not counted in the
    numerator). None ("N/A") when the model emitted zero claims — never a fabricated 0.0.
    """
    if total_emitted_claims == 0:
        return None
    return (supported + contradicted + unsupported) / total_emitted_claims


def classify_case_outcome(result: BenchmarkResult) -> dict:
    """Non-exclusive outcome flags for one AGENT case — a case can carry more than one.

    - retrieval_failure: required tool/evidence was not successfully retrieved
    - structured_output_failure: schema/claim validity or zero-claim behavior prevented verification
    - grounding_failure: at least one CONTRADICTED or UNSUPPORTED verifiable claim
    - successful: retrieval succeeded, no structural failure, and every verifiable
      claim was supported

    Only meaningful for completed AGENT cases; VERIFIER_CHALLENGE cases and errored
    cases get all flags False (they're not part of model performance comparison).
    """
    if result.case_type != "AGENT" or result.status == "error":
        return {"retrieval_failure": False, "structured_output_failure": False, "grounding_failure": False, "successful": False}

    retrieval_failure = (
        (result.required_tool_recall is not None and result.required_tool_recall < 1.0)
        or (result.evidence_recall is not None and result.evidence_recall < 1.0)
    )
    structured_output_failure = (
        result.zero_claim
        or (result.structured_claim_validity_rate is not None and result.structured_claim_validity_rate < 1.0)
    )
    grounding_failure = result.contradicted > 0 or result.unsupported > 0
    successful = not retrieval_failure and not structured_output_failure and not grounding_failure

    return {
        "retrieval_failure": retrieval_failure,
        "structured_output_failure": structured_output_failure,
        "grounding_failure": grounding_failure,
        "successful": successful,
    }


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round(pct * (len(ordered) - 1))))
    return ordered[idx]


def patient_diversity(results: list[BenchmarkResult]) -> dict:
    """How spread out AGENT cases are across distinct synthetic patients.

    Only AGENT cases count — VERIFIER_CHALLENGE cases test the verifier,
    not the model's handling of a particular patient's data.
    """
    agent_results = [r for r in results if r.case_type == "AGENT"]
    if not agent_results:
        return {"unique_patients": 0, "cases_per_patient": {}, "max_cases_from_one_patient": None, "min_cases_per_represented_patient": None}

    counts: dict[str, int] = {}
    for r in agent_results:
        counts[r.patient_id] = counts.get(r.patient_id, 0) + 1

    return {
        "unique_patients": len(counts),
        "cases_per_patient": counts,
        "max_cases_from_one_patient": max(counts.values()),
        "min_cases_per_represented_patient": min(counts.values()),
    }


def results_by_difficulty(results: list[BenchmarkResult]) -> dict:
    """Group pass/fail/error counts by the engineering difficulty label."""
    grouped: dict[str, dict[str, int]] = {}
    for r in results:
        key = r.difficulty or "unlabeled"
        grouped.setdefault(key, {"total": 0, "passed": 0, "failed": 0, "error": 0})
        grouped[key]["total"] += 1
        grouped[key][r.status] += 1
    return grouped


def _agent_metrics_summary(agent_results: list[BenchmarkResult]) -> dict:
    """Compute the full agent-performance metric set for one group of completed AGENT results.

    Shared by the overall aggregate and every grouped-by-category/difficulty breakdown
    (see grouped_agent_metrics) so the exact same formulas apply everywhere. Every
    subgroup carries its own `n` — small subgroups should be read with that in mind,
    never as if they were the full-dataset numbers.
    """
    n = len(agent_results)
    recalls = [r.required_tool_recall for r in agent_results if r.required_tool_recall is not None]
    precisions = [r.tool_precision for r in agent_results if r.tool_precision is not None]
    exact_matches = [r for r in agent_results if r.exact_tool_match is not None]
    overcall_cases = [r for r in agent_results if r.tool_overcall_count > 0]
    evidence_recalls = [r.evidence_recall for r in agent_results if r.evidence_recall is not None]
    claim_validity_rates = [r.structured_claim_validity_rate for r in agent_results if r.structured_claim_validity_rate is not None]
    # Kept only as a distinctly-named secondary metric (mean_case_verifiable_coverage,
    # below) — this is a macro-average across cases with a claim, silently excluding
    # zero-claim cases from its denominator. It is NOT verifiable_claim_coverage.
    per_case_coverages = [r.verifiable_claim_coverage for r in agent_results if r.verifiable_claim_coverage is not None]

    supported = sum(r.supported for r in agent_results)
    contradicted = sum(r.contradicted for r in agent_results)
    unsupported = sum(r.unsupported for r in agent_results)
    unverifiable = sum(r.unverifiable for r in agent_results)
    verifiable = supported + contradicted + unsupported
    raw_emitted_claims = sum(r.total_emitted_claims for r in agent_results)

    zero_claim_cases = sum(1 for r in agent_results if r.zero_claim)

    total_latencies = [r.total_latency_seconds for r in agent_results if r.total_latency_seconds is not None]
    tool_latencies = [r.tool_call_latency_seconds for r in agent_results if r.tool_call_latency_seconds is not None]
    structured_latencies = [r.structured_latency_seconds for r in agent_results if r.structured_latency_seconds is not None]

    outcome_flags = [classify_case_outcome(r) for r in agent_results]

    return {
        "n": n,
        # --- retrieval (layer A) ---
        "tool_recall": _mean_or_none(recalls),
        "tool_precision": _mean_or_none(precisions),
        "exact_tool_match_rate": (
            sum(1 for r in exact_matches if r.exact_tool_match) / len(exact_matches) if exact_matches else None
        ),
        "tool_overcall_rate": (len(overcall_cases) / n) if n else None,
        "total_duplicate_tool_calls": sum(r.duplicate_tool_calls for r in agent_results),
        "evidence_recall": _mean_or_none(evidence_recalls),
        # --- structured output (layer B) ---
        "structured_claim_validity_rate": _mean_or_none(claim_validity_rates),
        # verifiable_claim_coverage: the documented micro-average — (SUPPORTED + CONTRADICTED
        # + UNSUPPORTED) / total_emitted_claims, computed from the group's TOTALS, not a mean
        # of individual cases' coverage. See docs/model-comparison.md, "Raw vs. parsed vs.
        # verifiable claim counts" for why a per-case average of this metric would be wrong
        # (it silently drops zero-claim cases instead of counting them as 0% coverage).
        "verifiable_claim_coverage": verifiable_claim_coverage(supported, contradicted, unsupported, raw_emitted_claims),
        # mean_case_verifiable_coverage: the OLD (incorrect-for-this-name) behavior, kept only
        # under this distinct name — the unweighted mean of each case's own coverage ratio,
        # among cases that emitted at least one claim. Never use this to answer "how much of
        # this model's total output was verifiable" — use verifiable_claim_coverage for that.
        "mean_case_verifiable_coverage": _mean_or_none(per_case_coverages),
        "zero_claim_cases": zero_claim_cases,
        "zero_claim_rate": (zero_claim_cases / n) if n else None,
        "malformed_attribute_claim_count": sum(r.malformed_attribute_claim_count for r in agent_results),
        "wrong_category_or_assertion_count": sum(r.wrong_category_or_assertion_count for r in agent_results),
        # raw_emitted_claims: every claim the model's structured output contained, valid or not
        # (== total_emitted_claims, kept under both names — see docs/model-comparison.md).
        "raw_emitted_claims": raw_emitted_claims,
        "total_emitted_claims": raw_emitted_claims,
        # parsed_claims: raw claims that survived MEVA's schema parsing (see agent._parse_agent_answer)
        # and were actually handed to the verifier — this is len(claims) per case, summed.
        "parsed_claims": sum(len(r.claims) for r in agent_results),
        # verifiable_claims: parsed claims MEVA's verifier could reach a real
        # SUPPORTED/CONTRADICTED/UNSUPPORTED verdict on (excludes UNVERIFIABLE).
        "verifiable_claims": verifiable,
        # --- grounding (layer C) — never called clinical accuracy/safety ---
        "total_claims": supported + contradicted + unsupported + unverifiable,
        "supported_claims": supported,
        "contradicted_claims": contradicted,
        "unsupported_claims": unsupported,
        "unverifiable_claims": unverifiable,
        "evidence_grounding_score": _grounding_score(supported, contradicted, unsupported),
        "contradiction_rate_among_verifiable": (contradicted / verifiable) if verifiable else None,
        "unsupported_rate_among_verifiable": (unsupported / verifiable) if verifiable else None,
        # --- case-outcome taxonomy (non-exclusive; see classify_case_outcome) ---
        "retrieval_failure_cases": sum(1 for f in outcome_flags if f["retrieval_failure"]),
        "structured_output_failure_cases": sum(1 for f in outcome_flags if f["structured_output_failure"]),
        "grounding_failure_cases": sum(1 for f in outcome_flags if f["grounding_failure"]),
        "successful_cases": sum(1 for f in outcome_flags if f["successful"]),
        # --- latency ---
        "median_total_latency_seconds": _median_or_none(total_latencies),
        "p25_total_latency_seconds": _percentile(total_latencies, 0.25),
        "p75_total_latency_seconds": _percentile(total_latencies, 0.75),
        "median_tool_call_latency_seconds": _median_or_none(tool_latencies),
        "median_structured_latency_seconds": _median_or_none(structured_latencies),
    }


def grouped_agent_metrics(agent_results: list[BenchmarkResult], key_fn) -> dict:
    """Run _agent_metrics_summary separately per group (e.g. by category or difficulty).

    Every group's summary includes its own `n` — callers must show it alongside any
    percentage so a 1-case group isn't read as if it meant the same as a 20-case one.
    """
    groups: dict[str, list[BenchmarkResult]] = {}
    for r in agent_results:
        key = key_fn(r) or "unlabeled"
        groups.setdefault(key, []).append(r)
    return {key: _agent_metrics_summary(rs) for key, rs in groups.items()}


def aggregate_metrics(results: list[BenchmarkResult]) -> dict:
    """Aggregate a benchmark run's results, keeping AGENT and VERIFIER_CHALLENGE performance separate.

    These are never combined into one score — a verifier-challenge case tests
    MEVA's verification code, not the local model, so mixing them would make
    both numbers meaningless. See docs/benchmarking.md.
    """
    total_cases = len(results)
    error_cases = sum(1 for r in results if r.status == "error")
    completed_cases = total_cases - error_cases

    agent_results = [r for r in results if r.case_type == "AGENT" and r.status != "error"]
    verifier_results = [r for r in results if r.case_type == "VERIFIER_CHALLENGE" and r.status != "error"]

    agent_metrics = {"agent_cases": len(agent_results), **_agent_metrics_summary(agent_results)}

    # --- verifier-challenge performance (run/reported once — never per model, see docs) ---
    verifier_success = [r for r in verifier_results if r.expected_status_achieved]
    verifier_metrics = {
        "verifier_challenge_cases": len(verifier_results),
        "verifier_challenge_success_rate": (
            len(verifier_success) / len(verifier_results) if verifier_results else None
        ),
        "cases": [
            {"case_id": r.case_id, "expected_status": r.expected_status, "achieved": r.expected_status_achieved}
            for r in verifier_results
        ],
    }

    return {
        "dataset": {
            "total_cases": total_cases,
            "completed_cases": completed_cases,
            "error_cases": error_cases,
        },
        "agent": agent_metrics,
        "verifier_challenge": verifier_metrics,
        "patient_diversity": patient_diversity(results),
        "by_difficulty": results_by_difficulty(results),
        "by_category_grouped": grouped_agent_metrics(agent_results, lambda r: r.category),
        "by_difficulty_grouped": grouped_agent_metrics(agent_results, lambda r: r.difficulty),
    }
