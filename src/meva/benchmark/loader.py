"""Load benchmark cases from a JSON dataset file."""

import json
from pathlib import Path

from meva.benchmark.models import BenchmarkCase

DEFAULT_DATASET = (Path(__file__).resolve().parent.parent.parent.parent / "benchmarks" / "v0.1" / "cases.json").resolve()


def load_cases(
    path: str | Path | None = None,
    category: str | None = None,
    limit: int | None = None,
) -> list[BenchmarkCase]:
    """Load benchmark cases, optionally filtered by category and/or limited in count.

    Filtering happens before limiting, so `limit=3, category="allergy"`
    returns up to 3 allergy cases, not the first 3 cases overall.
    """
    dataset_path = Path(path) if path else DEFAULT_DATASET
    if not dataset_path.exists():
        raise FileNotFoundError(f"Benchmark dataset not found: {dataset_path}")

    with dataset_path.open("r", encoding="utf-8") as f:
        raw_cases = json.load(f)

    cases = [BenchmarkCase(**raw) for raw in raw_cases]

    if category:
        cases = [c for c in cases if c.category == category]

    if limit is not None:
        cases = cases[:limit]

    return cases
