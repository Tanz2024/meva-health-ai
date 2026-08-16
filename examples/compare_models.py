"""Compare local Ollama models on MEVA's v0.3 benchmark.

Pilot (Stage 7C1, unchanged): a fixed 6-case pilot set.
    python3 examples/compare_models.py --models qwen3:4b llama3.2:3b --dataset v0.3 --cases 6

Full run (Stage 7C2): every v0.3 AGENT case, resumable, one model at a time if desired.
    python3 examples/compare_models.py --models qwen3:4b llama3.2:3b --dataset v0.3 --full --run-id v0.3-run1
    python3 examples/compare_models.py --model qwen3:4b --dataset v0.3 --full --run-id v0.3-run1
    python3 examples/compare_models.py --models qwen3:4b llama3.2:3b --dataset v0.3 --full --resume v0.3-run1

Runs models strictly sequentially (never in parallel) — see docs/model-comparison.md.
Only AGENT cases are used for model comparison; VERIFIER_CHALLENGE cases test MEVA's
verifier, not a model, and (in --full mode) run exactly once, separately.
"""

import argparse

from meva.benchmark.comparison import (
    agent_only,
    run_full_comparison,
    run_model_comparison,
    save_comparison_results,
    save_full_comparison_results,
)
from meva.benchmark.loader import load_cases
from meva.benchmark.validator import ValidationError, validate_dataset

DATASET_PATHS = {
    "v0.1": "benchmarks/v0.1/cases.json",
    "v0.2": "benchmarks/v0.2/cases.json",
    "v0.3": "benchmarks/v0.3/cases.json",
}

# The default 6-case pilot: 1 allergy, 1 medication, 1 condition, 1 observation,
# 1 empty-evidence, 1 multi-tool — the same case IDs for every model compared.
DEFAULT_PILOT_CASE_IDS = [
    "allergy-01", "medication-01", "condition-01", "observation-01", "empty-evidence-01", "multi-tool-01",
]


def _print_table(results):
    labels = [r.model for r in results]
    rows = [
        ("Tool recall", lambda m: m.get("tool_recall")),
        ("Tool precision", lambda m: m.get("tool_precision")),
        ("Exact tool match", lambda m: m.get("exact_tool_match_rate")),
        ("Evidence recall", lambda m: m.get("evidence_recall")),
        ("Structured validity", lambda m: m.get("structured_claim_validity_rate")),
        ("Verifiable coverage", lambda m: m.get("verifiable_claim_coverage")),
        ("Zero-claim rate", lambda m: m.get("zero_claim_rate")),
        ("Grounding score", lambda m: m.get("evidence_grounding_score")),
        ("Supported", lambda m: m.get("supported_claims")),
        ("Contradicted", lambda m: m.get("contradicted_claims")),
        ("Unsupported", lambda m: m.get("unsupported_claims")),
        ("Unverifiable", lambda m: m.get("unverifiable_claims")),
        ("Retrieval failures", lambda m: m.get("retrieval_failure_cases")),
        ("Structured failures", lambda m: m.get("structured_output_failure_cases")),
        ("Grounding failures", lambda m: m.get("grounding_failure_cases")),
        ("Successful cases", lambda m: m.get("successful_cases")),
        ("Median latency (s)", lambda m: m.get("median_total_latency_seconds")),
    ]

    col_width = max(20, *(len(label) for label in labels)) + 2
    header = "Model".ljust(22) + "".join(label.ljust(col_width) for label in labels)
    print(header)
    print("-" * len(header))
    for row_label, getter in rows:
        cells = [str(getter(r.agent_metrics)) for r in results]
        print(row_label.ljust(22) + "".join(c.ljust(col_width) for c in cells))


def main():
    parser = argparse.ArgumentParser(description="Compare local Ollama models on MEVA's v0.3 benchmark.")
    parser.add_argument("--models", nargs="+", default=None, help="Registered model names, e.g. qwen3:4b llama3.2:3b")
    parser.add_argument("--model", type=str, default=None, help="Run a single model (shorthand for --models <model>)")
    parser.add_argument("--dataset", type=str, default="v0.3", choices=list(DATASET_PATHS), help="Benchmark dataset version")
    parser.add_argument("--cases", type=int, default=None, help="Limit to the first N pilot case IDs (pilot mode only)")
    parser.add_argument("--case-ids", nargs="+", default=None, help="Explicit case IDs to run instead of the default pilot set (pilot mode only)")
    parser.add_argument("--pause-between-cases", type=float, default=5, help="Seconds to pause between cases (default: 5)")
    parser.add_argument("--pause-between-models", type=float, default=15, help="Seconds to pause between models (default: 15)")
    parser.add_argument("--full", action="store_true", help="Run the full v0.3 AGENT case set (resumable) instead of the 6-case pilot")
    parser.add_argument("--run-id", type=str, default=None, help="Run identifier for --full mode's resume file (default: auto-generated)")
    parser.add_argument("--resume", type=str, default=None, help="Resume a previous --full run by its run-id")
    args = parser.parse_args()

    models = args.models or ([args.model] if args.model else None)
    if not models:
        parser.error("--models or --model is required")

    all_cases = load_cases(path=DATASET_PATHS[args.dataset])
    try:
        validate_dataset(all_cases)
    except ValidationError as e:
        print(f"Dataset validation failed:\n{e}")
        return

    if args.full:
        agent_cases = agent_only(all_cases)
        verifier_cases = [c for c in all_cases if c.case_type == "VERIFIER_CHALLENGE"]
        run_id = args.resume or args.run_id or f"{args.dataset}-{'-'.join(m.replace(':', '_') for m in models)}"

        print("MEVA — Full Model Comparison (Stage 7C2)\n")
        print(f"Dataset: {args.dataset}")
        print(f"Run ID: {run_id}" + (" (resuming)" if args.resume else ""))
        print(f"Models (sequential, never parallel): {models}")
        print(f"AGENT cases: {len(agent_cases)}  |  VERIFIER_CHALLENGE cases: {len(verifier_cases)}\n")
        print("Note: this compares tool use, structured-output quality, and evidence grounding.")
        print("It is NOT a clinical safety or accuracy comparison. See docs/model-comparison.md.\n")

        model_results, verifier_results = run_full_comparison(
            models, agent_cases, verifier_cases, benchmark_version=args.dataset, run_id=run_id,
            pause_between_cases=args.pause_between_cases, pause_between_models=args.pause_between_models,
        )

        for r in model_results:
            print(f"\n=== {r.model} ===")
            print(f"  tag={r.ollama_tag} digest={r.digest} parameter_size={r.parameter_size} quantization={r.quantization}")
            print(f"  compatibility: tool_call_supported={r.compatibility.tool_call_supported} "
                  f"structured_output_supported={r.compatibility.structured_output_supported}")
            if r.compatibility.compatibility_error:
                print(f"  compatibility_error: {r.compatibility.compatibility_error}")
            print(f"  agent_case_count={r.agent_case_count}")

        print("\n" + "=" * 60)
        print("Comparison table\n")
        _print_table([r for r in model_results if r.agent_case_count > 0])

        json_path, md_path = save_full_comparison_results(
            model_results, verifier_results, [c.case_id for c in agent_cases], benchmark_version=args.dataset,
        )
        print(f"\nSaved JSON: {json_path}")
        print(f"Saved Markdown: {md_path}")
        return

    case_ids = args.case_ids or DEFAULT_PILOT_CASE_IDS
    if args.cases is not None:
        case_ids = case_ids[: args.cases]

    cases = agent_only([c for c in all_cases if c.case_id in case_ids])
    cases.sort(key=lambda c: case_ids.index(c.case_id))

    if not cases:
        print("No matching AGENT cases found for the given case IDs.")
        return

    print("MEVA — Multi-Model Comparison (pilot)\n")
    print(f"Dataset: {args.dataset}")
    print(f"Models (sequential, never parallel): {models}")
    print(f"Cases ({len(cases)}): {[c.case_id for c in cases]}\n")
    print("Note: this compares tool use, structured-output quality, and evidence grounding.")
    print("It is NOT a clinical safety or accuracy comparison. See docs/model-comparison.md.\n")

    results = run_model_comparison(
        models, cases, benchmark_version=args.dataset,
        pause_between_cases=args.pause_between_cases, pause_between_models=args.pause_between_models,
    )

    for r in results:
        print(f"\n=== {r.model} ===")
        print(f"  tag={r.ollama_tag} digest={r.digest} parameter_size={r.parameter_size} quantization={r.quantization}")
        print(f"  capabilities={r.capabilities}")
        print(f"  compatibility: tool_call_supported={r.compatibility.tool_call_supported} "
              f"structured_output_supported={r.compatibility.structured_output_supported}")
        if r.compatibility.compatibility_error:
            print(f"  compatibility_error: {r.compatibility.compatibility_error}")
        print(f"  effective_configuration: {r.effective_configuration}")

    print("\n" + "=" * 60)
    print("Comparison table\n")
    _print_table([r for r in results if r.agent_case_count > 0])

    output_path = save_comparison_results(results, benchmark_version=args.dataset)
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
