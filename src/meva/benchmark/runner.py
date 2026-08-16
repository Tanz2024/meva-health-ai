"""Run a list of BenchmarkCases through the graph, one at a time.

One failing case must never crash the whole benchmark run — the graph
itself isolates failures per case (see graph.py), and this runner adds
one more safety net around graph invocation itself.
"""

import time

from meva.benchmark.graph import build_graph
from meva.benchmark.models import BenchmarkCase, BenchmarkResult


def run_benchmark(
    cases: list[BenchmarkCase],
    model: str | None = None,
    base_url: str | None = None,
    agent_overrides: dict | None = None,
    pause_between_cases: float = 0,
    skip_case_ids: set | None = None,
    on_case_complete=None,
) -> list[BenchmarkResult]:
    """Run every case through MEVA's benchmark graph and return their results in order.

    `agent_overrides` — see build_graph()/docs/model-comparison.md.
    `pause_between_cases` (seconds) — a thermal-safety pause inserted before
    each case after the first *actually run* case. Does not guarantee thermal
    safety; it's a simple, honest throttle (see docs/model-comparison.md).
    `skip_case_ids` — case IDs to skip entirely (e.g. already completed in a
    prior, resumed run). Skipped cases are simply absent from the returned list.
    `on_case_complete(case_id, result)` — called after each case actually run,
    for callers that need to persist progress incrementally (see run_state.py).
    """
    graph = build_graph(model=model, base_url=base_url, agent_overrides=agent_overrides)
    skip_case_ids = skip_case_ids or set()
    results = []
    ran_any = False

    for case in cases:
        if case.case_id in skip_case_ids:
            continue

        if ran_any and pause_between_cases > 0:
            time.sleep(pause_between_cases)
        ran_any = True

        try:
            final_state = graph.invoke(
                {"case": case.model_dump()},
                config={"configurable": {"thread_id": case.case_id}},
            )
            result = BenchmarkResult(**final_state["result"])
        except Exception as e:
            # Last-resort isolation in case something outside the graph's own
            # per-node error handling still goes wrong (e.g. a malformed case).
            result = BenchmarkResult(
                case_id=case.case_id,
                category=case.category,
                case_type=case.case_type,
                difficulty=case.difficulty,
                patient_id=case.patient_id,
                question=case.question,
                expected_tools=case.expected_tools,
                expected_status=case.expected_status,
                status="error",
                error_type=type(e).__name__,
                error_message=str(e),
            )

        results.append(result)
        if on_case_complete:
            on_case_complete(case.case_id, result)

    return results
