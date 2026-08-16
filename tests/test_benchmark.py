"""Tests for MEVA's benchmark engine.

These tests never talk to a real Ollama server. The "contradiction"
category case is inherently offline (it bypasses the live model by
design), and for every other category we mock meva.ai.agent.run_agent
so the graph/runner logic is what's under test, not the model itself.
"""

from unittest.mock import patch

from meva.ai.ollama_client import RunMetrics
from meva.benchmark import aggregate_metrics, load_cases, run_benchmark, save_results
from meva.benchmark.loader import load_cases as loader_load_cases
from meva.benchmark.models import BenchmarkCase
from meva.verification.models import MedicalClaim

RICH_PATIENT_ID = "080b069b-5108-46b6-ecef-6aacd3b9ef3f"


def fake_agent_result(tool: str, arguments: dict, tool_result, answer: str, claims: list[dict]):
    """Build a fake meva.ai.agent.run_agent() return value."""
    return {
        "answer": answer,
        "claims": [MedicalClaim(**c) for c in claims],
        "log": [{"model": "fake-model", "question": "q", "tool": tool, "arguments": arguments, "result": tool_result, "error": None}],
        "metrics": {
            "tool_calls": [RunMetrics(total_duration=1_000_000_000, eval_count=10)],
            "final": RunMetrics(total_duration=500_000_000, eval_count=5),
        },
        "claim_quality": {"total_raw_claims": len(claims), "valid_claims": len(claims), "structured_claim_validity_rate": 1.0 if claims else None},
    }


# --- case loading --------------------------------------------------------

def test_benchmark_case_loading():
    cases = load_cases()
    assert len(cases) == 12
    assert all(isinstance(c, BenchmarkCase) for c in cases)


def test_filtering_by_category():
    cases = load_cases(category="allergy")
    assert len(cases) == 2
    assert all(c.category == "allergy" for c in cases)


def test_limiting_cases():
    cases = load_cases(limit=4)
    assert len(cases) == 4


def test_limit_and_category_combine_correctly():
    cases = load_cases(category="allergy", limit=1)
    assert len(cases) == 1
    assert cases[0].category == "allergy"


def test_zero_case_handling():
    cases = load_cases(category="not-a-real-category")
    assert cases == []
    results = run_benchmark(cases)
    assert results == []
    summary = aggregate_metrics(results)
    assert summary["dataset"]["total_cases"] == 0
    assert summary["agent"]["evidence_grounding_score"] == "N/A"
    assert summary["agent"]["median_total_latency_seconds"] is None


# --- graph execution (offline, contradiction case needs no mock) -----------

def test_graph_execution_contradiction_case():
    # Constructed inline against the current public dataset (see
    # data/synthetic/synthea/PROVENANCE.md) rather than loaded from v0.1's cases.json —
    # this is a graph-mechanism test, not a historical-results test, and v0.1's own
    # on-disk case file intentionally still references the removed historical patient
    # (see docs/historical-sample-data-provenance.md) and is left untouched.
    case = BenchmarkCase(
        case_id="contradiction-test", category="contradiction", patient_id=RICH_PATIENT_ID,
        question="Intentional contradiction test: does MEVA catch a false 'no allergies' claim?",
        expected_tools=[], description="Bypasses the live model; feeds a deliberately wrong claim straight into the verifier.",
        expected_status="CONTRADICTED",
        injected_claim={
            "text": "No allergies are recorded for this patient.", "patient_id": RICH_PATIENT_ID,
            "category": "allergy", "value": None, "assertion": "absent",
        },
    )
    results = run_benchmark([case])
    assert len(results) == 1
    result = results[0]
    assert result.status == "passed"
    assert result.contradicted == 1
    assert result.evidence_grounding_score == "0%"


# --- tool-selection comparison ---------------------------------------------

def test_tool_selection_correct_when_expected_tool_called():
    case = BenchmarkCase(
        case_id="t1", category="allergy", patient_id=RICH_PATIENT_ID,
        question="q", expected_tools=["get_allergies"], description="d", expected_status="SUPPORTED",
    )
    fake = fake_agent_result(
        "get_allergies", {"patient_id": RICH_PATIENT_ID}, [{"name": "Fish (substance)"}],
        "Fish allergy recorded.",
        [{"text": "Fish allergy", "patient_id": RICH_PATIENT_ID, "category": "allergy", "value": "Fish", "assertion": "present"}],
    )
    with patch("meva.benchmark.graph.run_agent_fn", return_value=fake):
        results = run_benchmark([case])

    assert results[0].tool_selection_correct is True
    assert results[0].status == "passed"


def test_tool_selection_incorrect_when_expected_tool_missing():
    case = BenchmarkCase(
        case_id="t2", category="multi_tool", patient_id=RICH_PATIENT_ID,
        question="q", expected_tools=["get_patient", "get_allergies"], description="d",
    )
    fake = fake_agent_result(
        "get_allergies", {"patient_id": RICH_PATIENT_ID}, [{"name": "Fish (substance)"}],
        "Fish allergy recorded.",
        [{"text": "Fish allergy", "patient_id": RICH_PATIENT_ID, "category": "allergy", "value": "Fish", "assertion": "present"}],
    )
    with patch("meva.benchmark.graph.run_agent_fn", return_value=fake):
        results = run_benchmark([case])

    assert results[0].tool_selection_correct is False
    assert results[0].status == "failed"


def test_tool_selection_correct_when_expected_tools_empty():
    case = BenchmarkCase(
        case_id="t3", category="allergy", patient_id=RICH_PATIENT_ID,
        question="q", expected_tools=[], description="d",
    )
    fake = fake_agent_result("get_allergies", {"patient_id": RICH_PATIENT_ID}, [], "No allergies.", [])
    with patch("meva.benchmark.graph.run_agent_fn", return_value=fake):
        results = run_benchmark([case])

    assert results[0].tool_selection_correct is True


# --- verification aggregation & score ---------------------------------------

def test_verification_aggregation_and_score():
    case = BenchmarkCase(
        case_id="t4", category="allergy", patient_id=RICH_PATIENT_ID,
        question="q", expected_tools=["get_allergies"], description="d", expected_status="SUPPORTED",
    )
    fake = fake_agent_result(
        "get_allergies", {"patient_id": RICH_PATIENT_ID}, [],
        "Two claims.",
        [
            {"text": "Fish allergy", "patient_id": RICH_PATIENT_ID, "category": "allergy", "value": "Fish", "assertion": "present"},
            {"text": "Latex allergy", "patient_id": RICH_PATIENT_ID, "category": "allergy", "value": "Latex", "assertion": "present"},
        ],
    )
    with patch("meva.benchmark.graph.run_agent_fn", return_value=fake):
        results = run_benchmark([case])

    result = results[0]
    assert result.supported == 1
    assert result.unsupported == 1
    assert result.evidence_grounding_score == "50%"
    assert result.status == "passed"  # expected_status SUPPORTED was achieved by at least one claim


def test_aggregate_metrics_across_multiple_results():
    case_a = BenchmarkCase(case_id="a", category="allergy", patient_id=RICH_PATIENT_ID, question="q", expected_tools=["get_allergies"], description="d")
    case_b = BenchmarkCase(case_id="b", category="medication", patient_id=RICH_PATIENT_ID, question="q", expected_tools=["get_medications"], description="d")

    fake_a = fake_agent_result(
        "get_allergies", {}, [], "a",
        [{"text": "x", "patient_id": RICH_PATIENT_ID, "category": "allergy", "value": "Fish", "assertion": "present"}],
    )
    fake_b = fake_agent_result(
        "get_medications", {}, [], "b",
        [{"text": "y", "patient_id": RICH_PATIENT_ID, "category": "medication", "value": "Nonexistent", "assertion": "present"}],
    )

    with patch("meva.benchmark.graph.run_agent_fn", side_effect=[fake_a, fake_b]):
        results = run_benchmark([case_a, case_b])

    summary = aggregate_metrics(results)
    assert summary["dataset"]["total_cases"] == 2
    assert summary["dataset"]["completed_cases"] == 2
    assert summary["dataset"]["error_cases"] == 0
    assert summary["agent"]["total_claims"] == 2
    assert summary["agent"]["supported_claims"] == 1
    assert summary["agent"]["unsupported_claims"] == 1
    assert summary["agent"]["evidence_grounding_score"] == "50%"
    assert summary["agent"]["tool_recall"] == 1.0
    assert summary["agent"]["exact_tool_match_rate"] == 1.0
    assert summary["agent"]["median_total_latency_seconds"] == 1.5  # 1.0s tool-call + 0.5s structured, per fake


# --- error isolation ---------------------------------------------------

def test_error_isolation_does_not_crash_remaining_cases():
    case_bad = BenchmarkCase(case_id="bad", category="allergy", patient_id=RICH_PATIENT_ID, question="q", expected_tools=["get_allergies"], description="d")
    case_good = BenchmarkCase(case_id="good", category="allergy", patient_id=RICH_PATIENT_ID, question="q", expected_tools=["get_allergies"], description="d")

    fake_good = fake_agent_result("get_allergies", {}, [], "ok", [])

    def side_effect(question, model=None, base_url=None):
        if question == "q" and side_effect.calls == 0:
            side_effect.calls += 1
            raise RuntimeError("simulated Ollama connection failure")
        return fake_good
    side_effect.calls = 0

    with patch("meva.benchmark.graph.run_agent_fn", side_effect=side_effect):
        results = run_benchmark([case_bad, case_good])

    assert results[0].status == "error"
    assert results[0].error_type == "RuntimeError"
    assert "simulated" in results[0].error_message
    assert results[1].status == "passed"


def test_error_result_does_not_leak_paths_or_secrets():
    case = BenchmarkCase(case_id="bad2", category="allergy", patient_id=RICH_PATIENT_ID, question="q", expected_tools=["get_allergies"], description="d")

    with patch("meva.benchmark.graph.run_agent_fn", side_effect=RuntimeError("boom")):
        results = run_benchmark([case])

    assert results[0].status == "error"
    assert "/Users/" not in (results[0].error_message or "")


# --- result serialization ---------------------------------------------------

def test_result_serialization_round_trip(tmp_path):
    case = BenchmarkCase(case_id="s1", category="allergy", patient_id=RICH_PATIENT_ID, question="q", expected_tools=["get_allergies"], description="d")
    fake = fake_agent_result(
        "get_allergies", {}, [], "ok",
        [{"text": "x", "patient_id": RICH_PATIENT_ID, "category": "allergy", "value": "Fish", "assertion": "present"}],
    )
    with patch("meva.benchmark.graph.run_agent_fn", return_value=fake):
        results = run_benchmark([case])

    output_path = save_results(results, results_dir=tmp_path)
    assert output_path.exists()

    import json
    payload = json.loads(output_path.read_text())
    assert payload["meva_version"]
    assert payload["model"]
    assert payload["ollama_config"]["temperature"] == 0
    assert payload["ollama_config"]["seed"] == 42
    assert len(payload["cases"]) == 1
    assert payload["aggregate"]["dataset"]["total_cases"] == 1


# --- old tests still pass: verified by running the full suite, not here. ---
