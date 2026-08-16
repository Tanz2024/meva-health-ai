"""Benchmark MEVA's local pipeline latency on a single fixed question.

Runs the same allergy question 3 times with MEVA's evaluation-mode
settings (temperature=0, seed=42) and reports each run's timing (as
actually reported by Ollama — never invented), plus the median total
latency across runs.

Usage:
    python3 examples/benchmark_single_run.py
"""

import statistics

from meva.ai.agent import run_agent
from meva.verification import build_report

QUESTION = "What allergies are recorded for patient 6895f047-ab31-c293-b335-374256e01eb1?"
RUNS = 3


def _seconds(metrics_list) -> float | None:
    """Sum total_duration (ns) across a list of RunMetrics, in seconds. None if any is missing."""
    totals = [m.total_duration for m in metrics_list]
    if any(t is None for t in totals):
        return None
    return sum(totals) / 1e9


def main():
    print("MEVA — Single-Run Latency Benchmark\n")
    print(f"Question:\n{QUESTION}\n")

    total_latencies = []

    for run_number in range(1, RUNS + 1):
        result = run_agent(QUESTION)
        report = build_report(result["answer"], result["claims"])

        tool_call_seconds = _seconds(result["metrics"]["tool_calls"])
        final_seconds = _seconds([result["metrics"]["final"]])
        total_seconds = None
        if tool_call_seconds is not None and final_seconds is not None:
            total_seconds = tool_call_seconds + final_seconds
            total_latencies.append(total_seconds)

        print(f"Run {run_number}")
        print(f"  tool-call latency:       {tool_call_seconds:.2f}s" if tool_call_seconds is not None else "  tool-call latency:       (not reported)")
        print(f"  structured-answer latency: {final_seconds:.2f}s" if final_seconds is not None else "  structured-answer latency: (not reported)")
        print(f"  total latency:           {total_seconds:.2f}s" if total_seconds is not None else "  total latency:           (not reported)")
        print(f"  number of tool calls:    {len(result['log'])}")
        print(f"  claims generated:        {len(result['claims'])}")
        print(f"  grounding score:         {report.summary.grounding_score}")
        print()

    if total_latencies:
        print(f"Median total latency across {len(total_latencies)} run(s): {statistics.median(total_latencies):.2f}s")
    else:
        print("Median total latency: (not reported — Ollama didn't return timing for at least one run)")


if __name__ == "__main__":
    main()
