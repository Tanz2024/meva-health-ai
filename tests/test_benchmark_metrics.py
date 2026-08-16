"""Tests for MEVA's Stage 7B benchmark metrics: tool recall/precision/exact-match/
over-calling, duplicate-call tracking, evidence recall, and agent/verifier
aggregate separation. Fully offline.
"""

from unittest.mock import patch

from meva.ai.ollama_client import RunMetrics
from meva.benchmark import aggregate_metrics, run_benchmark
from meva.benchmark.metrics import evidence_recall, tool_metrics
from meva.benchmark.models import BenchmarkCase, ExpectedEvidence

RICH_PATIENT_ID = "080b069b-5108-46b6-ecef-6aacd3b9ef3f"
SPARSE_PATIENT_ID = "d15b23ed-02d5-3e28-efbd-2604425317c5"  # genuinely has zero allergies


def fake_agent_result(tools_and_results: list[tuple[str, dict, object]], answer: str, claims: list[dict]):
    """Build a fake meva.ai.agent.run_agent() return value with one or more tool calls."""
    log = [
        {"model": "fake", "question": "q", "tool": tool, "arguments": args, "result": result, "error": None}
        for tool, args, result in tools_and_results
    ]
    return {
        "answer": answer,
        "claims": [__import__("meva.verification.models", fromlist=["MedicalClaim"]).MedicalClaim(**c) for c in claims],
        "log": log,
        "metrics": {
            "tool_calls": [RunMetrics(total_duration=1_000_000_000)] * max(len(log), 1),
            "final": RunMetrics(total_duration=500_000_000),
        },
        "claim_quality": {"total_raw_claims": len(claims), "valid_claims": len(claims), "structured_claim_validity_rate": 1.0 if claims else None},
    }


# --- tool_metrics() unit tests ------------------------------------------

def test_tool_recall_full_and_partial():
    assert tool_metrics(["get_allergies"], ["get_allergies"])["required_tool_recall"] == 1.0
    assert tool_metrics(["get_allergies", "get_medications"], ["get_allergies"])["required_tool_recall"] == 0.5
    assert tool_metrics([], ["get_allergies"])["required_tool_recall"] is None


def test_tool_precision():
    # 1 of 2 unique calls were expected
    stats = tool_metrics(["get_allergies"], ["get_allergies", "get_conditions"])
    assert stats["tool_precision"] == 0.5
    assert tool_metrics(["get_allergies"], [])["tool_precision"] is None


def test_exact_tool_match():
    assert tool_metrics(["get_allergies"], ["get_allergies"])["exact_tool_match"] is True
    assert tool_metrics(["get_allergies"], ["get_allergies", "get_conditions"])["exact_tool_match"] is False
    assert tool_metrics(["get_allergies", "get_medications"], ["get_allergies"])["exact_tool_match"] is False


def test_tool_overcall_count():
    stats = tool_metrics(["get_allergies"], ["get_allergies", "get_conditions", "get_medications"])
    assert stats["tool_overcall_count"] == 2
    assert tool_metrics(["get_allergies"], ["get_allergies"])["tool_overcall_count"] == 0


def test_duplicate_tool_calls():
    stats = tool_metrics(["get_allergies"], ["get_allergies", "get_allergies", "get_allergies"])
    assert stats["unique_tool_calls"] == 1
    assert stats["total_tool_calls"] == 3
    assert stats["duplicate_tool_calls"] == 2


# --- evidence_recall() unit tests ---------------------------------------

def test_evidence_recall_all_found():
    facts = [ExpectedEvidence(category="allergy", value="Fish", source_tool="get_allergies")]
    log = [{"tool": "get_allergies", "result": [{"name": "Fish (substance)", "id": "x"}]}]
    assert evidence_recall(facts, log) == 1.0


def test_evidence_recall_partial():
    facts = [
        ExpectedEvidence(category="allergy", value="Fish", source_tool="get_allergies"),
        ExpectedEvidence(category="allergy", value="Aspirin", source_tool="get_allergies"),
    ]
    log = [{"tool": "get_allergies", "result": [{"name": "Fish (substance)", "id": "x"}]}]
    assert evidence_recall(facts, log) == 0.5


def test_evidence_recall_unavailable_when_no_facts():
    assert evidence_recall([], [{"tool": "get_allergies", "result": []}]) is None


# --- agent vs verifier-challenge separation ------------------------------

def test_agent_and_verifier_challenge_results_are_separated():
    agent_case = BenchmarkCase(
        case_id="a1", category="allergy", patient_id=RICH_PATIENT_ID,
        question="q", expected_tools=["get_allergies"], description="d",
    )
    challenge_case = BenchmarkCase(
        case_id="v1", category="verifier_challenge", case_type="VERIFIER_CHALLENGE",
        patient_id=RICH_PATIENT_ID, question="q", expected_tools=[], description="d",
        expected_status="CONTRADICTED",
        injected_claim={"text": "No allergies.", "patient_id": RICH_PATIENT_ID, "category": "allergy", "value": None, "assertion": "absent"},
    )
    fake = fake_agent_result(
        [("get_allergies", {}, [{"name": "Fish (substance)", "id": "x"}])],
        "Fish allergy.",
        [{"text": "Fish", "patient_id": RICH_PATIENT_ID, "category": "allergy", "value": "Fish", "assertion": "present"}],
    )
    with patch("meva.benchmark.graph.run_agent_fn", return_value=fake):
        results = run_benchmark([agent_case, challenge_case])

    by_id = {r.case_id: r for r in results}
    assert by_id["a1"].case_type == "AGENT"
    assert by_id["v1"].case_type == "VERIFIER_CHALLENGE"

    summary = aggregate_metrics(results)
    assert summary["agent"]["agent_cases"] == 1
    assert summary["verifier_challenge"]["verifier_challenge_cases"] == 1
    # the agent's real claim never leaks into verifier-challenge counts and vice versa
    assert summary["agent"]["supported_claims"] == 1
    assert summary["verifier_challenge"]["verifier_challenge_success_rate"] == 1.0


def test_empty_evidence_case_scores_supported_not_error():
    case = BenchmarkCase(
        case_id="empty-1", category="empty_evidence", patient_id=SPARSE_PATIENT_ID,
        question="q", expected_tools=["get_allergies"], description="d", expected_status="SUPPORTED",
    )
    fake = fake_agent_result(
        [("get_allergies", {}, [])],
        "No allergies are recorded.",
        [{"text": "No allergies", "patient_id": SPARSE_PATIENT_ID, "category": "allergy", "value": None, "assertion": "absent"}],
    )
    with patch("meva.benchmark.graph.run_agent_fn", return_value=fake):
        results = run_benchmark([case])

    assert results[0].status == "passed"
    assert results[0].supported == 1
    assert results[0].evidence_grounding_score == "100%"


def test_evidence_recall_computed_through_full_graph_run():
    """Regression test: BenchmarkCase.expected_evidence_facts are already ExpectedEvidence
    objects (parsed by pydantic on construction) by the time finalize_result sees them —
    re-wrapping them a second time used to crash with a TypeError."""
    case = BenchmarkCase(
        case_id="evidence-1", category="allergy", patient_id=RICH_PATIENT_ID,
        question="q", expected_tools=["get_allergies"], description="d",
        expected_evidence_facts=[{"category": "allergy", "value": "Fish", "source_tool": "get_allergies"}],
    )
    fake = fake_agent_result(
        [("get_allergies", {}, [{"name": "Fish (substance)", "id": "x"}])],
        "Fish allergy.",
        [{"text": "Fish", "patient_id": RICH_PATIENT_ID, "category": "allergy", "value": "Fish", "assertion": "present"}],
    )
    with patch("meva.benchmark.graph.run_agent_fn", return_value=fake):
        results = run_benchmark([case])

    assert results[0].status == "passed"
    assert results[0].evidence_recall == 1.0


# --- Stage 7B.5: diversity + structured claim validity aggregation --------

def test_patient_diversity_metrics_correct():
    from meva.benchmark.metrics import patient_diversity

    case_a = BenchmarkCase(case_id="a", category="allergy", patient_id="p1", question="q", expected_tools=["get_allergies"], description="d")
    case_b = BenchmarkCase(case_id="b", category="medication", patient_id="p1", question="q", expected_tools=["get_medications"], description="d")
    case_c = BenchmarkCase(case_id="c", category="condition", patient_id="p2", question="q", expected_tools=["get_conditions"], description="d")

    fake = fake_agent_result([("get_allergies", {}, [])], "ok", [])
    with patch("meva.benchmark.graph.run_agent_fn", return_value=fake):
        results = run_benchmark([case_a, case_b, case_c])

    diversity = patient_diversity(results)
    assert diversity["unique_patients"] == 2
    assert diversity["cases_per_patient"] == {"p1": 2, "p2": 1}
    assert diversity["max_cases_from_one_patient"] == 2
    assert diversity["min_cases_per_represented_patient"] == 1


def test_structured_claim_validity_rate_aggregated():
    case = BenchmarkCase(case_id="v1", category="allergy", patient_id=RICH_PATIENT_ID, question="q", expected_tools=["get_allergies"], description="d")
    fake = fake_agent_result(
        [("get_allergies", {}, [{"name": "Fish (substance)", "id": "x"}])],
        "Fish allergy.",
        [{"text": "Fish", "patient_id": RICH_PATIENT_ID, "category": "allergy", "value": "Fish", "assertion": "present"}],
    )
    # Simulate a model that produced 2 raw claims, only 1 of which was valid.
    fake["claim_quality"] = {"total_raw_claims": 2, "valid_claims": 1, "structured_claim_validity_rate": 0.5}

    with patch("meva.benchmark.graph.run_agent_fn", return_value=fake):
        results = run_benchmark([case])

    assert results[0].structured_claim_validity_rate == 0.5

    summary = aggregate_metrics(results)
    assert summary["agent"]["structured_claim_validity_rate"] == 0.5


def test_verifier_challenge_claim_quality_is_not_applicable():
    case = BenchmarkCase(
        case_id="vc-1", category="verifier_challenge", case_type="VERIFIER_CHALLENGE",
        patient_id=RICH_PATIENT_ID, question="q", expected_tools=[], description="d", expected_status="CONTRADICTED",
        injected_claim={"text": "No allergies.", "patient_id": RICH_PATIENT_ID, "category": "allergy", "value": None, "assertion": "absent"},
    )
    results = run_benchmark([case])
    assert results[0].structured_claim_validity_rate is None
