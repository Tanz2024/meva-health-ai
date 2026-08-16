"""MEVA's benchmark workflow, built with LangGraph.

    START -> load_case -> run_agent -+-> (on error) -> finalize_result -> END
                                      +-> (ok)        -> verify_answer -> calculate_metrics -> finalize_result -> END

Every node calls existing MEVA modules (meva.ai.agent, meva.verification) —
this file contains no FHIR parsing, no tool-selection logic, and no
verification rules of its own. It only wires the existing pieces
together and keeps one failing case from crashing the whole run.
"""

from typing import Any, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from meva.ai.agent import run_agent as run_agent_fn
from meva.benchmark.metrics import classify_case_outcome, evidence_recall, extract_latencies, tool_metrics, verifiable_claim_coverage
from meva.benchmark.models import BenchmarkCase, BenchmarkResult
from meva.verification.models import MedicalClaim
from meva.verification.verifier import build_report


def _is_verifier_challenge(case: BenchmarkCase) -> bool:
    """A case is a verifier challenge if explicitly typed so, or (legacy v0.1) category=='contradiction'."""
    return bool(case.injected_claim) and (case.case_type == "VERIFIER_CHALLENGE" or case.category == "contradiction")


class BenchmarkState(TypedDict, total=False):
    """The graph's state. Kept JSON-serializable — every value is a plain dict/list/str."""

    case: dict
    agent_result: dict | None
    tool_calls: list[str]
    evidence: list[dict]
    claims: list[dict]
    claim_quality: dict | None
    verification_report: dict | None
    metrics: dict | None
    error: dict | None
    result: dict | None


def load_case(state: BenchmarkState) -> dict:
    """Validate the case is well-formed before running it. No side effects."""
    BenchmarkCase(**state["case"])  # raises if malformed — caught by the runner, not here
    return {}


def _make_run_agent_node(model: str | None, base_url: str | None, agent_overrides: dict | None = None):
    """agent_overrides lets a specific model's real capabilities (see meva.models.discovery)
    override run_agent()'s defaults — e.g. a model without "thinking" support gets
    tool_call_think=False instead of erroring. Omit a key to use run_agent()'s own default,
    which is what every model uses unless it genuinely can't support it (see docs/model-comparison.md)."""
    agent_overrides = agent_overrides or {}

    def run_agent(state: BenchmarkState) -> dict:
        case = BenchmarkCase(**state["case"])

        # VERIFIER_CHALLENGE cases test the verifier directly with a deliberately wrong
        # claim, instead of hoping a live model produces a wrong answer on cue.
        # See docs/benchmarking.md for why this can't rely on live model output.
        if _is_verifier_challenge(case):
            claim = MedicalClaim(**case.injected_claim)
            return {
                "agent_result": {"answer": case.description, "log": []},
                "tool_calls": [],
                "evidence": [],
                "claims": [claim.model_dump()],
                "claim_quality": None,  # not model output — not applicable, see docs/benchmarking.md
                "metrics": {"tool_calls": [], "final": None},
            }

        try:
            agent_result = run_agent_fn(case.question, model=model, base_url=base_url, **agent_overrides)
        except Exception as e:
            return {"error": {"error_type": type(e).__name__, "message": str(e)}}

        tool_calls = [entry["tool"] for entry in agent_result["log"]]
        metrics = {
            "tool_calls": [m.model_dump() for m in agent_result["metrics"]["tool_calls"]],
            "final": agent_result["metrics"]["final"].model_dump() if agent_result["metrics"]["final"] else None,
        }
        return {
            "agent_result": {"answer": agent_result["answer"], "log": agent_result["log"]},
            "tool_calls": tool_calls,
            "evidence": agent_result["log"],
            "claims": [c.model_dump() for c in agent_result["claims"]],
            "claim_quality": agent_result["claim_quality"],
            "metrics": metrics,
        }

    return run_agent


def verify_answer(state: BenchmarkState) -> dict:
    case = BenchmarkCase(**state["case"])
    claims = [MedicalClaim(**c) for c in state["claims"]]
    answer = state["agent_result"]["answer"]
    report = build_report(answer, claims)
    return {"verification_report": report.model_dump()}


def calculate_metrics(state: BenchmarkState) -> dict:
    latencies = extract_latencies(state["metrics"])
    merged = dict(state["metrics"] or {})
    merged["latencies"] = latencies
    return {"metrics": merged}


def finalize_result(state: BenchmarkState) -> dict:
    case = BenchmarkCase(**state["case"])
    case_type = "VERIFIER_CHALLENGE" if _is_verifier_challenge(case) else "AGENT"

    if state.get("error"):
        result = BenchmarkResult(
            case_id=case.case_id,
            category=case.category,
            case_type=case_type,
            difficulty=case.difficulty,
            patient_id=case.patient_id,
            question=case.question,
            expected_tools=case.expected_tools,
            expected_status=case.expected_status,
            status="error",
            error_type=state["error"]["error_type"],
            error_message=state["error"]["message"],
        )
        return {"result": result.model_dump()}

    tool_calls = state.get("tool_calls", [])
    tool_stats = tool_metrics(case.expected_tools, tool_calls)
    # Legacy Stage 7A rule, kept for backward compatibility (see models.py).
    tool_selection_correct = set(case.expected_tools).issubset(set(tool_calls))

    report = state["verification_report"]
    summary = report["summary"]

    latencies = (state.get("metrics") or {}).get("latencies", {})

    recall = evidence_recall(case.expected_evidence_facts, state.get("evidence", []))
    claim_quality = state.get("claim_quality")
    structured_claim_validity_rate = claim_quality["structured_claim_validity_rate"] if claim_quality else None

    # total_emitted_claims / zero_claim: for VERIFIER_CHALLENGE cases (claim_quality is
    # None — see _make_run_agent_node), the single injected claim is not model output, so
    # it's not counted here; zero_claim only applies to real AGENT model output.
    total_emitted_claims = claim_quality.get("total_raw_claims", 0) if claim_quality else 0
    zero_claim = case_type == "AGENT" and total_emitted_claims == 0
    coverage = verifiable_claim_coverage(
        summary["supported"], summary["contradicted"], summary["unsupported"], total_emitted_claims,
    )

    expected_status_achieved = (
        case.expected_status is None
        or any(c["status"] == case.expected_status for c in report["claims"])
    )
    status = "passed" if tool_selection_correct and expected_status_achieved else "failed"

    result = BenchmarkResult(
        case_id=case.case_id,
        category=case.category,
        case_type=case_type,
        difficulty=case.difficulty,
        patient_id=case.patient_id,
        question=case.question,
        tool_calls=tool_calls,
        expected_tools=case.expected_tools,
        tool_selection_correct=tool_selection_correct,
        unique_tool_calls=tool_stats["unique_tool_calls"],
        total_tool_calls=tool_stats["total_tool_calls"],
        duplicate_tool_calls=tool_stats["duplicate_tool_calls"],
        required_tool_recall=tool_stats["required_tool_recall"],
        tool_precision=tool_stats["tool_precision"],
        exact_tool_match=tool_stats["exact_tool_match"],
        tool_overcall_count=tool_stats["tool_overcall_count"],
        evidence_recall=recall,
        structured_claim_validity_rate=structured_claim_validity_rate,
        total_emitted_claims=total_emitted_claims,
        zero_claim=zero_claim,
        verifiable_claim_coverage=coverage,
        malformed_attribute_claim_count=claim_quality.get("malformed_attribute_claim_count", 0) if claim_quality else 0,
        wrong_category_or_assertion_count=claim_quality.get("wrong_category_or_assertion_count", 0) if claim_quality else 0,
        answer=state["agent_result"]["answer"],
        claims=[c["claim"] for c in report["claims"]],
        supported=summary["supported"],
        contradicted=summary["contradicted"],
        unsupported=summary["unsupported"],
        unverifiable=summary["unverifiable"],
        evidence_grounding_score=summary["grounding_score"],
        expected_status=case.expected_status,
        expected_status_achieved=expected_status_achieved,
        tool_call_latency_seconds=latencies.get("tool_call_seconds"),
        structured_latency_seconds=latencies.get("structured_seconds"),
        total_latency_seconds=latencies.get("total_seconds"),
        status=status,
    )
    outcome = classify_case_outcome(result)
    result = result.model_copy(update=outcome)
    return {"result": result.model_dump()}


def _route_after_run_agent(state: BenchmarkState) -> str:
    return "error" if state.get("error") else "ok"


def build_graph(
    model: str | None = None,
    base_url: str | None = None,
    checkpointer: Any = None,
    agent_overrides: dict | None = None,
):
    """Build and compile MEVA's benchmark graph.

    `agent_overrides` (e.g. {"tool_call_think": False}) lets a specific
    model's real capabilities override run_agent()'s defaults — see
    docs/model-comparison.md. Every model uses the same defaults unless
    it genuinely can't support one.

    An in-memory checkpointer is used by default — enough for a single
    process run and for unit tests. See docs/benchmarking.md for why a
    persistent checkpointer will matter once benchmarks run long enough
    that resuming after a crash (rather than restarting from case 1)
    becomes worthwhile.
    """
    graph = StateGraph(BenchmarkState)

    graph.add_node("load_case", load_case)
    graph.add_node("run_agent", _make_run_agent_node(model, base_url, agent_overrides))
    graph.add_node("verify_answer", verify_answer)
    graph.add_node("calculate_metrics", calculate_metrics)
    graph.add_node("finalize_result", finalize_result)

    graph.add_edge(START, "load_case")
    graph.add_edge("load_case", "run_agent")
    graph.add_conditional_edges(
        "run_agent", _route_after_run_agent, {"error": "finalize_result", "ok": "verify_answer"}
    )
    graph.add_edge("verify_answer", "calculate_metrics")
    graph.add_edge("calculate_metrics", "finalize_result")
    graph.add_edge("finalize_result", END)

    return graph.compile(checkpointer=checkpointer or InMemorySaver())
