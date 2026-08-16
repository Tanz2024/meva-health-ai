"""Run MEVA's benchmark suite against the local Ollama model.

Usage:
    python3 examples/run_benchmark.py
    python3 examples/run_benchmark.py --cases 3
    python3 examples/run_benchmark.py --category allergy
    python3 examples/run_benchmark.py --dataset benchmarks/v0.2/cases.json --cases 5
    python3 examples/run_benchmark.py --dataset benchmarks/v0.2/cases.json --category verifier_challenge

Requires a running local Ollama server (see docs/local-ai.md) unless
only running VERIFIER_CHALLENGE cases, which never call the model.
Local inference is slow, so this defaults to a small number of cases
rather than running the full suite automatically.
"""

import argparse

from meva.benchmark import aggregate_metrics, load_cases, run_benchmark, save_results
from meva.benchmark.validator import ValidationError, validate_dataset

DEFAULT_CASE_LIMIT = 3


def main():
    parser = argparse.ArgumentParser(description="Run MEVA's benchmark suite.")
    parser.add_argument("--dataset", type=str, default=None, help="Path to a cases.json file (default: benchmarks/v0.1/cases.json)")
    parser.add_argument("--cases", type=int, default=DEFAULT_CASE_LIMIT, help=f"Max cases to run (default: {DEFAULT_CASE_LIMIT})")
    parser.add_argument("--category", type=str, default=None, help="Only run cases in this category")
    parser.add_argument("--skip-validation", action="store_true", help="Skip the dataset validator (not recommended)")
    args = parser.parse_args()

    all_cases = load_cases(path=args.dataset, category=args.category)

    if not args.skip_validation:
        try:
            warnings = validate_dataset(all_cases)
        except ValidationError as e:
            print(f"Dataset validation failed:\n{e}")
            return
        for warning in warnings:
            print(f"Warning: {warning}")

    cases = all_cases[: args.cases]

    if not cases:
        print("No matching benchmark cases found.")
        return

    print("MEVA — Benchmark Run\n")
    print(f"Running {len(cases)} case(s){f' (category={args.category})' if args.category else ''}:\n")
    for case in cases:
        print(f"  - {case.case_id} ({case.category}, {case.case_type})")
    print()

    results = run_benchmark(cases)

    for result in results:
        print(f"[{result.status.upper()}] {result.case_id} ({result.case_type})")
        if result.case_type == "AGENT":
            print(f"  tools: {result.tool_calls} (expected: {result.expected_tools})")
            print(f"  tool recall: {result.required_tool_recall}  precision: {result.tool_precision}  "
                  f"exact match: {result.exact_tool_match}  overcalls: {result.tool_overcall_count}  "
                  f"duplicate calls: {result.duplicate_tool_calls}")
            if result.evidence_recall is not None:
                print(f"  evidence recall: {result.evidence_recall}")
        if result.status == "error":
            print(f"  error: {result.error_type}: {result.error_message}")
        else:
            print(f"  grounding score: {result.evidence_grounding_score} "
                  f"(supported={result.supported}, contradicted={result.contradicted}, "
                  f"unsupported={result.unsupported}, unverifiable={result.unverifiable})")
            if result.total_latency_seconds is not None:
                print(f"  latency: {result.total_latency_seconds:.2f}s")
        print()

    summary = aggregate_metrics(results)
    print("Dataset:", summary["dataset"])
    print("\nAgent performance:")
    for key, value in summary["agent"].items():
        print(f"  {key}: {value}")
    print("\nVerifier-challenge performance:")
    for key, value in summary["verifier_challenge"].items():
        print(f"  {key}: {value}")

    output_path = save_results(results)
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
