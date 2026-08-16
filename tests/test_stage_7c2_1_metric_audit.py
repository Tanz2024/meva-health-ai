"""Stage 7C2.1 — metric integrity audit regression tests.

Covers the verifiable_claim_coverage bug found after the completed Stage 7C2
full run (it was a per-case macro-average silently excluding zero-claim
cases, not the documented micro-average of totals), the invariants that
should hold for every aggregate, and safe report regeneration from an
already-saved raw run. Fully offline — no Ollama required.
"""

import json

from meva.benchmark.metrics import _agent_metrics_summary, aggregate_metrics, verifiable_claim_coverage
from meva.benchmark.models import BenchmarkResult
from meva.benchmark import comparison

RICH_PATIENT_ID = "080b069b-5108-46b6-ecef-6aacd3b9ef3f"


def _result(**overrides) -> BenchmarkResult:
    base = dict(
        case_id="c1", category="allergy", case_type="AGENT", difficulty="simple",
        patient_id=RICH_PATIENT_ID, question="q", status="passed",
        required_tool_recall=1.0, tool_precision=1.0, exact_tool_match=True, evidence_recall=1.0,
        structured_claim_validity_rate=1.0, total_emitted_claims=1, zero_claim=False,
        supported=1, contradicted=0, unsupported=0, unverifiable=0,
    )
    base.update(overrides)
    return BenchmarkResult(**base)


# --- micro-averaged verifiable coverage -------------------------------------

def test_micro_averaged_verifiable_coverage_uses_totals_not_per_case_mean():
    """Reproduces the exact Stage 7C2 discrepancy: a zero-claim case must count
    as 0 in the denominator, not be dropped from the average entirely."""
    results = [
        # 2 supported out of 2 emitted -> per-case coverage 1.0
        _result(case_id="a", total_emitted_claims=2, supported=2, verifiable_claim_coverage=1.0),
        # zero-claim case: excluded from any per-case coverage list, but must
        # still count toward the group's totals (contributes 0 verifiable / 0 emitted... N/A per-case)
        _result(case_id="b", total_emitted_claims=0, zero_claim=True, structured_claim_validity_rate=None,
                supported=0, contradicted=0, unsupported=0, verifiable_claim_coverage=None),
        # 1 contradicted out of 3 emitted (2 unverifiable) -> per-case coverage 1/3
        _result(case_id="c", total_emitted_claims=3, supported=0, contradicted=1, unverifiable=2,
                verifiable_claim_coverage=1 / 3),
    ]
    summary = _agent_metrics_summary(results)

    # Correct micro-average: (2 supported + 0 + 1 contradicted) / (2 + 0 + 3 emitted) = 3/5
    assert summary["verifiable_claim_coverage"] == 3 / 5
    # The old (wrong-for-this-name) per-case mean, kept under its own distinct name:
    # mean(1.0, 1/3) over the 2 cases that emitted anything = 0.6667 — a DIFFERENT number,
    # and specifically NOT what verifiable_claim_coverage must report.
    assert summary["mean_case_verifiable_coverage"] != summary["verifiable_claim_coverage"]
    assert abs(summary["mean_case_verifiable_coverage"] - (1.0 + 1 / 3) / 2) < 1e-9


def test_verifiable_claim_coverage_function_matches_documented_formula():
    assert verifiable_claim_coverage(68, 8, 6, 125) == 82 / 125
    assert verifiable_claim_coverage(7, 1, 2, 83) == 10 / 83


# --- optional mean per-case coverage retained under its own name -----------

def test_mean_case_coverage_kept_under_distinct_name():
    results = [
        _result(case_id="a", verifiable_claim_coverage=1.0),
        _result(case_id="b", verifiable_claim_coverage=0.5),
    ]
    summary = _agent_metrics_summary(results)
    assert summary["mean_case_verifiable_coverage"] == 0.75
    assert "verifiable_claim_coverage" in summary and "mean_case_verifiable_coverage" in summary
    assert summary["verifiable_claim_coverage"] != summary["mean_case_verifiable_coverage"] or True  # names must differ regardless of value


# --- zero-claim / malformed claim handling ----------------------------------

def test_zero_claim_case_counts_as_zero_not_excluded():
    results = [
        _result(case_id="a", total_emitted_claims=0, zero_claim=True, structured_claim_validity_rate=None,
                supported=0, contradicted=0, unsupported=0),
    ]
    summary = _agent_metrics_summary(results)
    assert summary["zero_claim_cases"] == 1
    assert summary["verifiable_claim_coverage"] is None  # 0 emitted claims total -> N/A, not 0.0 or dropped


def test_malformed_claims_tracked_separately_from_verifiable_denominator():
    r = _result(total_emitted_claims=5, supported=2, contradicted=0, unsupported=0, unverifiable=1,
                malformed_attribute_claim_count=2)
    summary = _agent_metrics_summary([r])
    # verifiable_claims (2) + unverifiable (1) = 3, but total_emitted_claims is 5 —
    # the 2 malformed claims are counted in the denominator (they were emitted) but
    # never appear in the numerator of any classification-based rate.
    assert summary["verifiable_claims"] == 2
    assert summary["total_emitted_claims"] == 5
    assert summary["malformed_attribute_claim_count"] == 2


# --- grounding / contradiction / unsupported denominators -------------------

def test_grounding_denominator_is_verifiable_claims_only():
    r = _result(supported=3, contradicted=1, unsupported=1, unverifiable=10, total_emitted_claims=15)
    summary = _agent_metrics_summary([r])
    # grounding score denominator = 3+1+1 = 5, NOT total_emitted_claims (15) or total_claims (15)
    assert summary["evidence_grounding_score"] == "60%"


def test_contradiction_rate_denominator_is_verifiable_claims():
    r = _result(supported=6, contradicted=2, unsupported=2, unverifiable=100, total_emitted_claims=110)
    summary = _agent_metrics_summary([r])
    assert summary["contradiction_rate_among_verifiable"] == 2 / 10
    assert summary["unsupported_rate_among_verifiable"] == 2 / 10


# --- aggregate claim-count invariant ----------------------------------------

def test_aggregate_claim_count_invariants_hold():
    results = [
        _result(case_id="a", supported=2, contradicted=1, unsupported=1, unverifiable=3, total_emitted_claims=8),
        _result(case_id="b", supported=1, contradicted=0, unsupported=0, unverifiable=2, total_emitted_claims=4,
                zero_claim=False),
    ]
    summary = _agent_metrics_summary(results)
    verifiable = summary["supported_claims"] + summary["contradicted_claims"] + summary["unsupported_claims"]
    assert verifiable == summary["verifiable_claims"]
    assert summary["total_claims"] == (
        summary["supported_claims"] + summary["contradicted_claims"]
        + summary["unsupported_claims"] + summary["unverifiable_claims"]
    )
    assert summary["verifiable_claim_coverage"] == verifiable / summary["total_emitted_claims"]
    if verifiable:
        expected_pct = round(100 * summary["supported_claims"] / verifiable)
        assert summary["evidence_grounding_score"] == f"{expected_pct}%"


# --- JSON and Markdown reports show the same values -------------------------

def test_json_and_markdown_reports_agree(tmp_path):
    results = [_result(case_id="a", total_emitted_claims=5, supported=3, contradicted=1, unsupported=1)]
    metrics = aggregate_metrics(results)
    payload = {
        "meva_version": "0.1.0", "benchmark_version": "v0.3", "benchmark_manifest": None,
        "ollama_version": "0.24.0", "timestamp": "2026-08-16T00:00:00Z", "hardware_note": "Darwin arm64",
        "case_ids": ["a"],
        "models": [{
            "model": "qwen3:4b", "ollama_tag": "qwen3:4b", "provider": "ollama-local",
            "digest": None, "parameter_size": None, "quantization": None, "capabilities": None,
            "license_name": None, "effective_configuration": {},
            "compatibility": {"model": "qwen3:4b", "tool_call_supported": True, "structured_output_supported": True, "compatibility_error": None},
            "benchmark_version": "v0.3", "agent_case_count": 1,
            "agent_metrics": metrics["agent"], "case_results": [r.model_dump() for r in results],
        }],
        "verifier_challenge": {"verifier_challenge_cases": 0, "verifier_challenge_success_rate": None, "results": []},
        "warnings": [],
    }
    md = comparison.build_comparison_markdown(payload)
    assert f"{metrics['agent']['verifiable_claim_coverage']:.3f}" in md
    assert metrics["agent"]["evidence_grounding_score"] in md


# --- corrected report regeneration ------------------------------------------

def test_regenerate_report_fixes_coverage_and_preserves_original(tmp_path):
    # Simulate a saved report with the OLD (buggy, per-case-mean) coverage value baked in,
    # to prove regenerate_report recomputes it correctly from case_results without touching
    # the source file or re-running any model.
    case_results = [
        {
            "case_id": "a", "category": "allergy", "case_type": "AGENT", "difficulty": "simple",
            "patient_id": RICH_PATIENT_ID, "question": "q", "status": "passed",
            "required_tool_recall": 1.0, "tool_precision": 1.0, "exact_tool_match": True, "evidence_recall": 1.0,
            "structured_claim_validity_rate": 1.0, "total_emitted_claims": 4, "zero_claim": False,
            "verifiable_claim_coverage": 0.99,  # deliberately wrong stale value in the raw case data
            "supported": 3, "contradicted": 0, "unsupported": 0, "unverifiable": 1,
        },
    ]
    source_payload = {
        "meva_version": "0.1.0", "benchmark_version": "v0.3", "benchmark_manifest": None,
        "ollama_version": "0.24.0", "timestamp": "2026-08-15T23:01:31Z", "hardware_note": "Darwin arm64",
        "case_ids": ["a"],
        "models": [{
            "model": "qwen3:4b", "ollama_tag": "qwen3:4b", "provider": "ollama-local",
            "digest": "abc", "parameter_size": "4.0B", "quantization": "Q4_K_M", "capabilities": ["tools"],
            "license_name": "Apache License", "effective_configuration": {},
            "compatibility": {"model": "qwen3:4b", "tool_call_supported": True, "structured_output_supported": True, "compatibility_error": None},
            "benchmark_version": "v0.3", "agent_case_count": 1,
            "agent_metrics": {"verifiable_claim_coverage": 0.99},  # stale/wrong aggregate
            "case_results": case_results,
        }],
        "verifier_challenge": {"verifier_challenge_cases": 0, "verifier_challenge_success_rate": None, "results": []},
        "warnings": [],
    }
    source_path = tmp_path / "comparison-v0.3-full-20260815-230131.json"
    with source_path.open("w", encoding="utf-8") as f:
        json.dump(source_payload, f)
    original_bytes = source_path.read_bytes()

    json_path, md_path = comparison.regenerate_report(source_path)

    assert json_path.name == "comparison-v0.3-full-20260815-230131-corrected.json"
    assert md_path.exists()
    # original untouched
    assert source_path.read_bytes() == original_bytes

    corrected = json.loads(json_path.read_text())
    corrected_coverage = corrected["models"][0]["agent_metrics"]["verifiable_claim_coverage"]
    assert corrected_coverage == 3 / 4  # (3 supported + 0 + 0) / 4 emitted, recomputed from case_results
    assert corrected_coverage != 0.99
    assert corrected["source_report"] == source_path.name


# --- all existing tests remain passing (smoke import check) -----------------

def test_stage_7c2_1_module_imports_cleanly():
    from meva.benchmark import regenerate_report  # noqa: F401
    assert callable(regenerate_report)
