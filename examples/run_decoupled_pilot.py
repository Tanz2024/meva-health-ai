"""Stage 7D1 — DECOUPLED claim extraction, 6-case pilot.

Reads already-saved qwen3:4b/llama3.2:3b natural-language answers from a
completed Stage 7C2 comparison report (no source-model inference is rerun),
runs each saved answer through a FIXED local extractor (qwen3:4b) and
MEVA's existing deterministic verifier, and reports END_TO_END vs
DECOUPLED metrics side by side — never combined. See docs/decoupled-evaluation.md.

Usage:
    python3 examples/run_decoupled_pilot.py \
      --source-report results/comparisons/comparison-v0.3-full-20260815-230131-corrected.json \
      --extractor-model qwen3:4b
"""

import argparse
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

from meva.ai.ollama_client import base_url as ollama_base_url
from meva.benchmark.metrics import aggregate_metrics
from meva.benchmark.models import BenchmarkResult
from meva.benchmark.reporter import MEVA_VERSION
from meva.extraction.extractor import EXTRACTION_KEEP_ALIVE, EXTRACTION_SEED, EXTRACTION_TEMPERATURE, EXTRACTION_THINK, run_decoupled_case
from meva.extraction.metrics import decoupled_grounding_metrics, extractor_quality_metrics
from meva.models.discovery import describe_model, get_ollama_version
from meva.models.registry import get_model_config

DEFAULT_RESULTS_DIR = (Path(__file__).resolve().parent.parent / "results" / "extraction").resolve()

# The exact same 6 case IDs used for the Stage 7C1 pilot — see docs/model-comparison.md.
PILOT_CASE_IDS = [
    "allergy-01", "medication-01", "condition-01", "observation-01", "empty-evidence-01", "multi-tool-01",
]

EXTRACTOR_BIAS_WARNING = (
    "The initial decoupled experiment uses qwen3:4b as the fixed claim extractor. "
    "This may introduce extractor-specific bias and should be tested with another "
    "extractor in future work."
)


def _hardware_note() -> str:
    return f"{platform.system()} {platform.machine()}"


def load_pilot_case_results(source_report_path: str | Path) -> dict[str, list[BenchmarkResult]]:
    """{model_name: [BenchmarkResult, ...]} for the pilot case IDs, from a saved comparison report."""
    with Path(source_report_path).open("r", encoding="utf-8") as f:
        payload = json.load(f)

    by_model = {}
    for model_entry in payload["models"]:
        cases = [
            BenchmarkResult(**cr) for cr in model_entry.get("case_results", [])
            if cr["case_id"] in PILOT_CASE_IDS
        ]
        cases.sort(key=lambda r: PILOT_CASE_IDS.index(r.case_id))
        if cases:
            by_model[model_entry["model"]] = cases
    return by_model


def run_pilot(source_report_path: str | Path, extractor_model: str, base_url: str | None = None) -> dict:
    by_model = load_pilot_case_results(source_report_path)

    base_config = get_model_config(extractor_model)
    extractor_config = describe_model(base_config, base_url=base_url)

    per_model = {}
    for source_model, end_to_end_results in by_model.items():
        end_to_end_metrics = aggregate_metrics(end_to_end_results)["agent"]

        decoupled_case_results = []
        extraction_results = []
        for r in end_to_end_results:
            decoupled = run_decoupled_case(
                case_id=r.case_id, category=r.category, difficulty=r.difficulty, patient_id=r.patient_id,
                source_model=source_model, question=r.question, answer_text=r.answer or "",
                extractor_model=extractor_config.ollama_tag, base_url=base_url,
            )
            decoupled_case_results.append(decoupled)
            extraction_results.append(decoupled.extraction_result)

        per_model[source_model] = {
            "case_ids": [r.case_id for r in end_to_end_results],
            "end_to_end": {
                "mode": "END_TO_END",
                "cases": len(end_to_end_results),
                "structured_claim_validity_rate": end_to_end_metrics.get("structured_claim_validity_rate"),
                "verifiable_claim_coverage": end_to_end_metrics.get("verifiable_claim_coverage"),
                "evidence_grounding_score": end_to_end_metrics.get("evidence_grounding_score"),
                "supported_claims": end_to_end_metrics.get("supported_claims"),
                "contradicted_claims": end_to_end_metrics.get("contradicted_claims"),
                "unsupported_claims": end_to_end_metrics.get("unsupported_claims"),
                "unverifiable_claims": end_to_end_metrics.get("unverifiable_claims"),
            },
            "decoupled": decoupled_grounding_metrics(decoupled_case_results),
            "extractor_quality": extractor_quality_metrics(extraction_results),
            "decoupled_case_results": [r.model_dump() for r in decoupled_case_results],
        }

    payload = {
        "meva_version": MEVA_VERSION,
        "evaluation_type": "DECOUPLED claim extraction pilot (Stage 7D1)",
        "ollama_version": get_ollama_version(base_url),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hardware_note": _hardware_note(),
        "source_report": str(source_report_path),
        "pilot_case_ids": PILOT_CASE_IDS,
        "extractor": {
            "model": extractor_config.name, "ollama_tag": extractor_config.ollama_tag,
            "digest": extractor_config.digest, "parameter_size": extractor_config.parameter_size,
            "quantization": extractor_config.quantization, "capabilities": extractor_config.capabilities,
            "temperature": EXTRACTION_TEMPERATURE, "seed": EXTRACTION_SEED, "think": EXTRACTION_THINK,
            "keep_alive": EXTRACTION_KEEP_ALIVE,
        },
        "models": per_model,
        "limitations": [
            EXTRACTOR_BIAS_WARNING,
            "Model-assisted extraction is not deterministic parsing — only the settings used are fixed, "
            "not the guarantee of byte-identical output across runs. Final verification remains deterministic Python.",
            "This is a 6-case pilot per source model (12 extraction runs total), not the full v0.3 AGENT set.",
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
    lines = ["# MEVA Decoupled Claim Extraction — Stage 7D1 Pilot", ""]
    lines.append(
        "Compares END_TO_END (model answers AND self-encodes claims) against DECOUPLED "
        "(model answers, a fixed extractor encodes claims) for the same saved answers. "
        "These are never combined into one score — they measure different things."
    )
    lines.append("")
    lines.append(f"- Extractor: `{payload['extractor']['ollama_tag']}` (digest `{payload['extractor']['digest']}`)")
    lines.append(f"- Extraction settings: temperature={payload['extractor']['temperature']}, "
                  f"seed={payload['extractor']['seed']}, think={payload['extractor']['think']}")
    lines.append(f"- Pilot case IDs: {payload['pilot_case_ids']}")
    lines.append("")

    for model, data in payload["models"].items():
        lines.append(f"## {model}")
        lines.append("")
        lines.append("| | END_TO_END | DECOUPLED |")
        lines.append("|---|---|---|")
        e2e, dec = data["end_to_end"], data["decoupled"]
        lines.append(f"| Validity | {_fmt(e2e['structured_claim_validity_rate'])} (structured) | "
                      f"{_fmt(data['extractor_quality']['extracted_claim_validity_rate'])} (extractor) |")
        lines.append(f"| Verifiable coverage | {_fmt(e2e['verifiable_claim_coverage'])} | {_fmt(dec['verifiable_claim_coverage'])} |")
        lines.append(f"| Grounding score | {e2e['evidence_grounding_score']} | {dec['evidence_grounding_score']} |")
        lines.append(f"| Supported/Contradicted/Unsupported/Unverifiable | "
                      f"{e2e['supported_claims']}/{e2e['contradicted_claims']}/{e2e['unsupported_claims']}/{e2e['unverifiable_claims']} | "
                      f"{dec['supported_claims']}/{dec['contradicted_claims']}/{dec['unsupported_claims']}/{dec['unverifiable_claims']} |")
        lines.append("")
        lines.append(
            "Note: a DECOUPLED score changing from the END_TO_END score reflects a change in "
            "EVALUATION METHOD, not the tested model 'improving' or 'getting worse'."
        )
        lines.append("")

    lines.append("## Limitations")
    for limitation in payload["limitations"]:
        lines.append(f"- {limitation}")
    lines.append("")
    return "\n".join(lines) + "\n"


def save_pilot_results(payload: dict, results_dir: str | Path | None = None) -> tuple[Path, Path]:
    directory = Path(results_dir) if results_dir else DEFAULT_RESULTS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = directory / f"decoupled-v0.3-pilot-{stamp}.json"
    md_path = directory / f"decoupled-v0.3-pilot-{stamp}.md"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    md_path.write_text(build_markdown(payload), encoding="utf-8")
    return json_path, md_path


def main():
    parser = argparse.ArgumentParser(description="Run the Stage 7D1 decoupled-extraction pilot.")
    parser.add_argument("--source-report", required=True, help="Path to a saved Stage 7C2 comparison JSON")
    parser.add_argument("--extractor-model", default="qwen3:4b", help="Registered model name to use as the fixed extractor")
    args = parser.parse_args()

    print("MEVA — Decoupled Claim Extraction Pilot (Stage 7D1)\n")
    print(f"Source report: {args.source_report}")
    print(f"Extractor model: {args.extractor_model}")
    print(f"Pilot case IDs: {PILOT_CASE_IDS}\n")
    print("Note: DECOUPLED evaluation does not prove clinical correctness or safety.\n")

    payload = run_pilot(args.source_report, args.extractor_model)

    for model, data in payload["models"].items():
        print(f"=== {model} ===")
        print(f"  END_TO_END: {data['end_to_end']}")
        print(f"  DECOUPLED:  {data['decoupled']}")
        print(f"  Extractor quality: {data['extractor_quality']}")
        print()

    json_path, md_path = save_pilot_results(payload)
    print(f"Saved JSON: {json_path}")
    print(f"Saved Markdown: {md_path}")


if __name__ == "__main__":
    main()
