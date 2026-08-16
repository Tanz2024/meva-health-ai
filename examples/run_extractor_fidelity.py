"""Stage 7D2 / 7D2.1 — extractor fidelity audit against dev or holdout fixtures.

Schema validity does not prove the extractor captures what an answer
actually said. This runs the fixed extractor over a fixture set and
measures deterministic claim-matching precision/recall/F1, negative-
assertion preservation, attribute accuracy, and per-error-type counts.

Usage:
    python3 examples/run_extractor_fidelity.py --fixture-set dev --extractor-model qwen3:4b
    python3 examples/run_extractor_fidelity.py --fixture-set holdout --extractor-model qwen3:4b

The HOLDOUT run determines whether Stage 7D2/7D2.1 may proceed to the full
104-answer decoupled run — see meva.extraction.fidelity.passes_holdout_gate.
The DEV run is for prompt development only and is never used as the gate.
"""

import argparse
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

from meva.benchmark.reporter import MEVA_VERSION
from meva.extraction.extractor import EXTRACTION_SEED, EXTRACTION_TEMPERATURE, EXTRACTION_THINK
from meva.extraction.fidelity import (
    HOLDOUT_MIN_ATTRIBUTE_ACCURACY,
    HOLDOUT_MIN_F1,
    HOLDOUT_MIN_NEGATIVE_PRESERVATION,
    HOLDOUT_MIN_PRECISION,
    HOLDOUT_MIN_RECALL,
    evaluate_gold_fixtures,
)
from meva.extraction.prompt import EXTRACTION_PROMPT_VERSION, prompt_hash
from meva.models.discovery import describe_model, get_ollama_version
from meva.models.registry import get_model_config

FIXTURE_PATHS = {
    "dev": (Path(__file__).resolve().parent.parent / "data" / "extraction" / "dev_fixtures.json"),
    "holdout": (Path(__file__).resolve().parent.parent / "data" / "extraction" / "holdout_fixtures.json"),
}
DEFAULT_RESULTS_DIR = (Path(__file__).resolve().parent.parent / "results" / "extraction").resolve()


def _hardware_note() -> str:
    return f"{platform.system()} {platform.machine()}"


def build_markdown(payload: dict) -> str:
    m = payload["metrics"]
    fixture_set = payload["fixture_set"]
    lines = [f"# MEVA Extractor Fidelity Audit — {fixture_set.upper()} ({payload['stage']})", ""]
    lines.append(
        "Schema validity alone does not prove semantic extraction fidelity. This measures "
        "whether the fixed extractor captures claims actually stated, avoids inventing or "
        "dropping claims, preserves negative assertions, and refuses to repair wrong answers."
    )
    lines.append("")
    lines.append(f"- Extractor: `{payload['extractor']['ollama_tag']}` (digest `{payload['extractor']['digest']}`)")
    lines.append(f"- Prompt version: `{payload['extractor']['prompt_version']}` (hash `{payload['extractor']['prompt_hash']}`)")
    lines.append(f"- Fixture set: `{fixture_set}` ({m['fixture_count']} fixtures)")
    if fixture_set == "holdout":
        gate = payload["holdout_gate"]
        lines.append(f"- Holdout decision gate: **{'PASSED' if gate['passed'] else 'FAILED'}**")
        for check in ("claim_precision", "claim_recall", "claim_f1", "negative_claim_preservation_rate", "attribute_claim_accuracy"):
            lines.append(f"  - {check}: {'pass' if gate[check] else 'FAIL'}")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    for key in (
        "schema_success_rate", "claim_precision", "claim_recall", "claim_f1",
        "exact_claim_set_match_rate", "added_claim_rate", "missed_claim_rate",
        "negative_claim_preservation_rate", "attribute_claim_accuracy",
    ):
        lines.append(f"| {key} | {m.get(key)} |")
    lines.append("")
    lines.append("## Error type counts")
    lines.append("")
    lines.append("| Type | Count |")
    lines.append("|---|---|")
    for error_type, count in payload["error_counts"].items():
        lines.append(f"| {error_type} | {count} |")
    lines.append("")
    lines.append("## Per-fixture results")
    lines.append("")
    lines.append("| Fixture | Gold | Extracted | TP | FP | FN | Exact match |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in payload["fixture_results"]:
        lines.append(
            f"| {r['fixture_id']} | {r['gold_claim_count']} | {r['extracted_claim_count']} | "
            f"{r['true_positive_claims']} | {r['false_positive_claims']} | {r['false_negative_claims']} | "
            f"{r['exact_claim_set_match']} |"
        )
    lines.append("")
    lines.append(
        "## Extractor bias\n\n"
        "The initial decoupled experiment uses qwen3:4b as the fixed claim extractor. "
        "This may introduce extractor-specific bias and should be tested with another "
        "extractor in future work. qwen3:4b is simultaneously one of the evaluated source models.\n"
    )
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Run an extractor fidelity audit against dev or holdout fixtures.")
    parser.add_argument("--fixture-set", choices=["dev", "holdout"], required=True)
    parser.add_argument("--extractor-model", default="qwen3:4b")
    args = parser.parse_args()

    fixtures_path = FIXTURE_PATHS[args.fixture_set]
    fixtures = json.loads(fixtures_path.read_text())
    print(f"MEVA — Extractor Fidelity Audit ({args.fixture_set.upper()})\n")
    print(f"Fixture set: {args.fixture_set} ({fixtures_path.name}, {len(fixtures)} fixtures)")
    print(f"Extractor: {args.extractor_model}")
    print(f"Prompt version: {EXTRACTION_PROMPT_VERSION} (hash {prompt_hash()})\n")

    base_config = get_model_config(args.extractor_model)
    extractor_config = describe_model(base_config)

    result = evaluate_gold_fixtures(fixtures, extractor_model=extractor_config.ollama_tag)

    payload = {
        "meva_version": MEVA_VERSION,
        "stage": "Stage 7D2.1",
        "evaluation_type": f"Extractor fidelity audit ({args.fixture_set})",
        "fixture_set": args.fixture_set,
        "fixture_set_path": str(fixtures_path),
        "ollama_version": get_ollama_version(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hardware_note": _hardware_note(),
        "extractor": {
            "model": extractor_config.name, "ollama_tag": extractor_config.ollama_tag,
            "digest": extractor_config.digest, "parameter_size": extractor_config.parameter_size,
            "quantization": extractor_config.quantization,
            "temperature": EXTRACTION_TEMPERATURE, "seed": EXTRACTION_SEED, "think": EXTRACTION_THINK,
            "prompt_version": EXTRACTION_PROMPT_VERSION, "prompt_hash": prompt_hash(),
        },
        "holdout_gate_thresholds": {
            "claim_precision": HOLDOUT_MIN_PRECISION, "claim_recall": HOLDOUT_MIN_RECALL,
            "claim_f1": HOLDOUT_MIN_F1, "negative_claim_preservation_rate": HOLDOUT_MIN_NEGATIVE_PRESERVATION,
            "attribute_claim_accuracy": HOLDOUT_MIN_ATTRIBUTE_ACCURACY,
        },
        **result,
    }

    print("Metrics:", json.dumps(payload["metrics"], indent=2))
    print("\nError counts:", json.dumps(payload["error_counts"], indent=2))
    if args.fixture_set == "holdout":
        print(f"\nHoldout decision gate: {'PASSED' if payload['holdout_gate']['passed'] else 'FAILED'}")
        print(json.dumps(payload["holdout_gate"], indent=2))

    DEFAULT_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = DEFAULT_RESULTS_DIR / f"extractor-fidelity-{args.fixture_set}-{stamp}.json"
    md_path = DEFAULT_RESULTS_DIR / f"extractor-fidelity-{args.fixture_set}-{stamp}.md"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    md_path.write_text(build_markdown(payload), encoding="utf-8")
    print(f"\nSaved JSON: {json_path}")
    print(f"Saved Markdown: {md_path}")

    if args.fixture_set == "holdout" and not payload["holdout_gate"]["passed"]:
        print(
            "\nSTOPPING before the full 104-answer decoupled run — holdout fidelity did not "
            "meet the decision gate. See docs/claim-extraction-contract.md."
        )


if __name__ == "__main__":
    main()
