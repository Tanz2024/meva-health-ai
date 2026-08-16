"""MEVA's benchmark engine: turns MEVA's verification pipeline into a reproducible,
LangGraph-orchestrated benchmark framework.

This package contains no FHIR parsing, no verification rules, and no
agent logic of its own — it only loads cases, drives the existing
meva.ai/meva.verification pipeline through a small LangGraph workflow,
and reports the results. See docs/benchmarking.md.
"""

from meva.benchmark.comparison import (
    CompatibilityResult,
    ModelComparisonResult,
    build_comparison_markdown,
    check_compatibility,
    regenerate_report,
    run_full_comparison,
    run_model_comparison,
    save_comparison_results,
    save_full_comparison_results,
)
from meva.benchmark.graph import build_graph
from meva.benchmark.loader import load_cases
from meva.benchmark.metrics import aggregate_metrics, classify_case_outcome, verifiable_claim_coverage
from meva.benchmark.models import BenchmarkCase, BenchmarkResult
from meva.benchmark.reporter import save_results
from meva.benchmark.run_state import IncompatibleResumeError, RunState
from meva.benchmark.runner import run_benchmark

__all__ = [
    "BenchmarkCase",
    "BenchmarkResult",
    "load_cases",
    "build_graph",
    "run_benchmark",
    "aggregate_metrics",
    "classify_case_outcome",
    "verifiable_claim_coverage",
    "save_results",
    "CompatibilityResult",
    "ModelComparisonResult",
    "check_compatibility",
    "run_model_comparison",
    "save_comparison_results",
    "run_full_comparison",
    "save_full_comparison_results",
    "build_comparison_markdown",
    "regenerate_report",
    "RunState",
    "IncompatibleResumeError",
]
