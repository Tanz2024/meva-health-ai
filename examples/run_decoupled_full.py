"""Stage 7D2 — full 104-answer decoupled extraction over the saved Stage 7C2 corrected report.

Reads every saved AGENT answer (52 qwen3:4b + 52 llama3.2:3b) from a completed
Stage 7C2 comparison report — no source-model inference is rerun. Runs the
fixed extractor (qwen3:4b) over each saved answer, resumably, then reports
END_TO_END vs DECOUPLED metrics, claim recovery, grounding-failure
preservation, and method disagreements. See docs/decoupled-evaluation.md.

Usage:
    python3 examples/run_decoupled_full.py \
      --source-report results/comparisons/comparison-v0.3-full-20260815-230131-corrected.json \
      --extractor-model qwen3:4b \
      --run-id decoupled-full-run1 \
      --pause-between-answers 3
"""

import argparse
import json
import platform
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from meva.benchmark.metrics import aggregate_metrics
from meva.benchmark.models import BenchmarkResult
from meva.benchmark.reporter import MEVA_VERSION
from meva.extraction.extractor import EXTRACTION_KEEP_ALIVE, EXTRACTION_SEED, EXTRACTION_TEMPERATURE, EXTRACTION_THINK, run_decoupled_case
from meva.extraction.metrics import (
    claim_recovery,
    decoupled_grounding_metrics,
    extractor_quality_metrics,
    find_grounding_failure_preservation,
    find_method_disagreements,
    group_decoupled_metrics,
)
from meva.extraction.models import DecoupledCaseResult
from meva.extraction.run_state import ExtractionRunState, source_report_hash
from meva.models.discovery import describe_model, get_ollama_version
from meva.models.registry import get_model_config

DEFAULT_RESULTS_DIR = (Path(__file__).resolve().parent.parent / "results" / "extraction").resolve()

EXTRACTOR_BIAS_WARNING = (
    "The initial decoupled experiment uses qwen3:4b as the fixed claim extractor. "
    "This may introduce extractor-specific bias and should be tested with another "
    "extractor in future work. qwen3:4b is simultaneously one of the evaluated source models."
)


def _hardware_note() -> str:
    return f"{platform.system()} {platform.machine()}"


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round(pct * (len(ordered) - 1))))
    return ordered[idx]


def load_all_agent_answers(source_report_path: str | Path) -> dict[str, list[BenchmarkResult]]:
    """{model_name: [BenchmarkResult, ...]} for every saved AGENT case in a Stage 7C2 report."""
    with Path(source_report_path).open("r", encoding="utf-8") as f:
        payload = json.load(f)

    by_model = {}
    for model_entry in payload["models"]:
        cases = [BenchmarkResult(**cr) for cr in model_entry.get("case_results", [])]
        if cases:
            by_model[model_entry["model"]] = cases
    return by_model


def run_full_decoupled_evaluation(
    source_report_path: str | Path, extractor_model: str, run_id: str,
    base_url: str | None = None, pause_between_answers: float = 0, runs_dir=None,
) -> dict:
    by_model = load_all_agent_answers(source_report_path)
    source_models = sorted(by_model)
    case_ids = sorted({r.case_id for results in by_model.values() for r in results})

    base_config = get_model_config(extractor_model)
    extractor_config = describe_model(base_config, base_url=base_url)

    extraction_config = {
        "temperature": EXTRACTION_TEMPERATURE, "seed": EXTRACTION_SEED,
        "think": EXTRACTION_THINK, "keep_alive": EXTRACTION_KEEP_ALIVE,
    }
    report_hash = source_report_hash(source_report_path)

    state = ExtractionRunState.load_or_create(
        run_id, report_hash, extractor_config.ollama_tag, extractor_config.digest,
        source_models, case_ids, extraction_config, runs_dir=runs_dir,
    )

    ran_any = False
    for source_model, results in by_model.items():
        for r in results:
            if state.is_done(source_model, r.case_id):
                continue
            if ran_any and pause_between_answers > 0:
                time.sleep(pause_between_answers)
            ran_any = True

            decoupled = run_decoupled_case(
                case_id=r.case_id, category=r.category, difficulty=r.difficulty, patient_id=r.patient_id,
                source_model=source_model, question=r.question, answer_text=r.answer or "",
                extractor_model=extractor_config.ollama_tag, base_url=base_url,
            )
            state.record(source_model, r.case_id, decoupled.model_dump())

    per_model_report = {}
    all_extraction_latencies = []

    for source_model, end_to_end_results in by_model.items():
        decoupled_results = [DecoupledCaseResult(**d) for d in state.results_for(source_model)]
        extraction_results = [d.extraction_result for d in decoupled_results]

        end_to_end_metrics = aggregate_metrics(end_to_end_results)["agent"]
        decoupled_metrics = decoupled_grounding_metrics(decoupled_results)
        extractor_metrics = extractor_quality_metrics(extraction_results)
        recovery = claim_recovery(end_to_end_results, decoupled_results)
        preserved = find_grounding_failure_preservation(end_to_end_results, decoupled_results)
        disagreements = find_method_disagreements(end_to_end_results, decoupled_results)

        latencies = [
            d.extraction_result.metrics.get("total_duration") / 1e9
            for d in decoupled_results
            if d.extraction_result.metrics and d.extraction_result.metrics.get("total_duration") is not None
        ]
        all_extraction_latencies.extend(latencies)

        per_model_report[source_model] = {
            "case_count": len(end_to_end_results),
            "end_to_end": {
                "mode": "END_TO_END",
                "structured_claim_validity_rate": end_to_end_metrics.get("structured_claim_validity_rate"),
                "verifiable_claim_coverage": end_to_end_metrics.get("verifiable_claim_coverage"),
                "evidence_grounding_score": end_to_end_metrics.get("evidence_grounding_score"),
                "zero_claim_rate": end_to_end_metrics.get("zero_claim_rate"),
                "supported_claims": end_to_end_metrics.get("supported_claims"),
                "contradicted_claims": end_to_end_metrics.get("contradicted_claims"),
                "unsupported_claims": end_to_end_metrics.get("unsupported_claims"),
                "unverifiable_claims": end_to_end_metrics.get("unverifiable_claims"),
                # retrieval metrics are the ORIGINAL Stage 7C2 numbers — the extractor never
                # touches retrieval, so these are carried through unrecomputed.
                "tool_recall": end_to_end_metrics.get("tool_recall"),
                "evidence_recall": end_to_end_metrics.get("evidence_recall"),
            },
            "decoupled": decoupled_metrics,
            "extractor_quality": extractor_metrics,
            "claim_recovery": recovery,
            "grounding_failure_preservation": preserved,
            "method_disagreements": disagreements,
            "by_category": group_decoupled_metrics(decoupled_results, lambda r: r.category),
            "by_difficulty": group_decoupled_metrics(decoupled_results, lambda r: r.difficulty),
            "extraction_latency_seconds": {
                "median": statistics.median(latencies) if latencies else None,
                "p25": _percentile(latencies, 0.25),
                "p75": _percentile(latencies, 0.75),
            },
        }

    payload = {
        "meva_version": MEVA_VERSION,
        "evaluation_type": "Full decoupled claim extraction (Stage 7D2)",
        "ollama_version": get_ollama_version(base_url),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hardware_note": _hardware_note(),
        "source_report": str(source_report_path),
        "source_report_sha256": report_hash,
        "run_id": run_id,
        "extractor": {
            "model": extractor_config.name, "ollama_tag": extractor_config.ollama_tag,
            "digest": extractor_config.digest, "parameter_size": extractor_config.parameter_size,
            "quantization": extractor_config.quantization, "capabilities": extractor_config.capabilities,
            **extraction_config,
        },
        "case_ids": case_ids,
        "models": per_model_report,
        "overall_extraction_latency_seconds": {
            "median": statistics.median(all_extraction_latencies) if all_extraction_latencies else None,
            "p25": _percentile(all_extraction_latencies, 0.25),
            "p75": _percentile(all_extraction_latencies, 0.75),
        },
        "limitations": [
            EXTRACTOR_BIAS_WARNING,
            "Model-assisted extraction is not deterministic parsing — only the settings used are fixed.",
            "Method-disagreement causes are classified deterministically from available fields, not by an LLM judge.",
            "Grouped category/difficulty subgroups can be small — see each group's own n; no statistical "
            "significance claims are made.",
            "DECOUPLED evaluation does not prove clinical correctness or safety.",
        ],
    }
    return payload


def _fmt(v):
    if v is None:
        return "N/A"
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


def build_markdown(payload: dict) -> str:
    lines = ["# MEVA Full Decoupled Claim Extraction — Stage 7D2", ""]
    lines.append(
        "Every saved v0.3 AGENT answer (both source models) run through a fixed extractor "
        "(qwen3:4b) and MEVA's unchanged deterministic verifier. END_TO_END and DECOUPLED "
        "numbers are never combined."
    )
    lines.append("")
    lines.append(f"- Extractor: `{payload['extractor']['ollama_tag']}` (digest `{payload['extractor']['digest']}`)")
    lines.append(f"- Source report: `{payload['source_report']}`")
    lines.append(f"- Cases: {len(payload['case_ids'])}")
    lines.append("")

    for model, data in payload["models"].items():
        lines.append(f"## {model} (n={data['case_count']})")
        lines.append("")
        e2e, dec = data["end_to_end"], data["decoupled"]
        lines.append("| | END_TO_END | DECOUPLED |")
        lines.append("|---|---|---|")
        lines.append(f"| Validity | {_fmt(e2e['structured_claim_validity_rate'])} | {_fmt(data['extractor_quality']['extracted_claim_validity_rate'])} |")
        lines.append(f"| Verifiable coverage | {_fmt(e2e['verifiable_claim_coverage'])} | {_fmt(dec['verifiable_claim_coverage'])} |")
        lines.append(f"| Grounding score | {e2e['evidence_grounding_score']} | {dec['evidence_grounding_score']} |")
        lines.append(f"| Zero claims | {_fmt(e2e['zero_claim_rate'])} | {_fmt(data['extractor_quality']['zero_extracted_claim_rate'])} |")
        lines.append("")
        lines.append(f"Under the decoupled evaluation method, claim recovery: "
                      f"{data['claim_recovery']['claim_recovery_count']} cases "
                      f"({_fmt(data['claim_recovery']['claim_recovery_case_rate'])} rate).")
        lines.append(f"Grounding failures preserved across both methods: {len(data['grounding_failure_preservation'])} case(s).")
        lines.append(f"Method disagreements: {len(data['method_disagreements'])} case(s).")
        lines.append(f"Extraction latency (median/p25/p75, s): "
                      f"{_fmt(data['extraction_latency_seconds']['median'])} / "
                      f"{_fmt(data['extraction_latency_seconds']['p25'])} / "
                      f"{_fmt(data['extraction_latency_seconds']['p75'])}")
        lines.append("")

    lines.append("## Limitations")
    for limitation in payload["limitations"]:
        lines.append(f"- {limitation}")
    lines.append("")
    return "\n".join(lines) + "\n"


def save_full_results(payload: dict, results_dir=None) -> tuple[Path, Path]:
    directory = Path(results_dir) if results_dir else DEFAULT_RESULTS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = directory / f"decoupled-v0.3-full-{stamp}.json"
    md_path = directory / f"decoupled-v0.3-full-{stamp}.md"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    md_path.write_text(build_markdown(payload), encoding="utf-8")
    return json_path, md_path


def main():
    parser = argparse.ArgumentParser(description="Run the Stage 7D2 full decoupled extraction.")
    parser.add_argument("--source-report", required=True)
    parser.add_argument("--extractor-model", default="qwen3:4b")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--pause-between-answers", type=float, default=3)
    parser.add_argument("--resume", action="store_true", help="No-op flag for clarity — resuming is automatic given the same --run-id")
    args = parser.parse_args()

    print("MEVA — Full Decoupled Claim Extraction (Stage 7D2)\n")
    print(f"Source report: {args.source_report}")
    print(f"Extractor model: {args.extractor_model}")
    print(f"Run ID: {args.run_id}\n")

    payload = run_full_decoupled_evaluation(
        args.source_report, args.extractor_model, args.run_id, pause_between_answers=args.pause_between_answers,
    )

    for model, data in payload["models"].items():
        print(f"=== {model} ===")
        print(f"  END_TO_END: {data['end_to_end']}")
        print(f"  DECOUPLED:  {data['decoupled']}")
        print(f"  Claim recovery: {data['claim_recovery']}")
        print(f"  Grounding failures preserved: {len(data['grounding_failure_preservation'])}")
        print(f"  Method disagreements: {len(data['method_disagreements'])}")
        print()

    json_path, md_path = save_full_results(payload)
    print(f"Saved JSON: {json_path}")
    print(f"Saved Markdown: {md_path}")


if __name__ == "__main__":
    main()
