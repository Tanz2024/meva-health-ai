"""Save benchmark results to a timestamped local JSON file.

No private machine identifiers are collected — only a generic OS/CPU
architecture string (e.g. "Darwin arm64"), never a hostname, username,
or file path outside the project's own results/ directory.
"""

import json
import platform
from datetime import datetime, timezone
from pathlib import Path

from meva.ai.agent import EVAL_SEED, EVAL_TEMPERATURE, FINAL_STRUCTURED_THINK, TOOL_CALL_THINK
from meva.ai.ollama_client import base_url as ollama_base_url
from meva.ai.ollama_client import model_name
from meva.benchmark.metrics import aggregate_metrics
from meva.benchmark.models import BenchmarkResult

MEVA_VERSION = "0.1.0"
BENCHMARK_VERSION = "v0.1"

DEFAULT_RESULTS_DIR = (Path(__file__).resolve().parent.parent.parent.parent / "results").resolve()


def _hardware_note() -> str:
    """A generic, non-identifying OS/architecture string — never a hostname or username."""
    return f"{platform.system()} {platform.machine()}"


def build_report_payload(results: list[BenchmarkResult]) -> dict:
    """Assemble the full JSON-serializable benchmark report payload (without writing it)."""
    return {
        "meva_version": MEVA_VERSION,
        "benchmark_version": BENCHMARK_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": model_name(),
        "ollama_config": {
            "base_url": ollama_base_url(),
            "temperature": EVAL_TEMPERATURE,
            "seed": EVAL_SEED,
            "tool_call_think": TOOL_CALL_THINK,
            "final_structured_think": FINAL_STRUCTURED_THINK,
        },
        "hardware_note": _hardware_note(),
        "cases": [r.model_dump() for r in results],
        "aggregate": aggregate_metrics(results),
    }


def save_results(results: list[BenchmarkResult], results_dir: str | Path | None = None) -> Path:
    """Write a benchmark report to results/benchmark-YYYYMMDD-HHMMSS.json and return its path."""
    directory = Path(results_dir) if results_dir else DEFAULT_RESULTS_DIR
    directory.mkdir(parents=True, exist_ok=True)

    filename = f"benchmark-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    output_path = directory / filename

    payload = build_report_payload(results)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    return output_path
