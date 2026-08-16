"""Compare multiple local Ollama models on the exact same MEVA benchmark.

Every model runs the same cases, the same system prompt, the same
structured-claim schema, and the same deterministic verifier — see
docs/model-comparison.md for why this matters and what it can't tell you.

Models run strictly sequentially (never in parallel), with an optional
pause between cases and between models, and a best-effort unload of the
previous model before the next one starts.
"""

import json
import platform
import time
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from meva.ai.agent import run_agent as run_agent_fn
from meva.ai.ollama_client import base_url as ollama_base_url
from meva.benchmark.metrics import aggregate_metrics
from meva.benchmark.models import BenchmarkCase, BenchmarkResult
from meva.benchmark.reporter import MEVA_VERSION
from meva.benchmark.run_state import RunState
from meva.benchmark.runner import run_benchmark
from meva.models.config import ModelConfig
from meva.models.discovery import ModelNotInstalledError, describe_model, get_ollama_version, unload_model
from meva.models.registry import get_model_config

DEFAULT_COMPARISON_RESULTS_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent / "results" / "comparisons"
).resolve()

# A question that needs a tool call and always has evidence to describe back —
# a good minimal probe for "can this model use MEVA's tools and schema at all."
COMPATIBILITY_PATIENT_ID = "6895f047-ab31-c293-b335-374256e01eb1"


class CompatibilityResult(BaseModel):
    """Result of a minimal end-to-end probe: can this model use MEVA's tools and schema at all?"""

    model: str
    tool_call_supported: bool
    structured_output_supported: bool
    compatibility_error: str | None = None


class ModelComparisonResult(BaseModel):
    """Everything about one model's run of the (same) benchmark cases."""

    model: str
    ollama_tag: str
    provider: str
    digest: str | None = None
    parameter_size: str | None = None
    quantization: str | None = None
    capabilities: list[str] | None = None
    license_name: str | None = None
    effective_configuration: dict

    compatibility: CompatibilityResult

    benchmark_version: str
    agent_case_count: int

    # Kept as MEVA's existing separate sections — see meva.benchmark.metrics.aggregate_metrics.
    # Never combined into one score.
    agent_metrics: dict

    case_results: list[BenchmarkResult] = Field(default_factory=list)


def effective_agent_overrides(config: ModelConfig) -> dict:
    """The generation settings actually sent to run_agent() for this model."""
    return {
        "tool_call_think": config.tool_think,
        "final_structured_think": config.structured_think,
        "temperature": config.temperature,
        "seed": config.seed,
    }


def check_compatibility(
    config: ModelConfig, patient_id: str = COMPATIBILITY_PATIENT_ID, base_url: str | None = None,
) -> CompatibilityResult:
    """Run one real question through the full agent loop and confirm both
    tool-calling and structured output actually work for this model."""
    question = f"What allergies are recorded for patient {patient_id}?"
    try:
        result = run_agent_fn(
            question, model=config.ollama_tag, base_url=base_url, **effective_agent_overrides(config)
        )
    except Exception as e:
        return CompatibilityResult(
            model=config.name, tool_call_supported=False, structured_output_supported=False,
            compatibility_error=f"{type(e).__name__}: {e}",
        )

    tool_call_supported = len(result["log"]) > 0
    structured_output_supported = bool(result["claim_quality"]["schema_parsed"])

    return CompatibilityResult(
        model=config.name,
        tool_call_supported=tool_call_supported,
        structured_output_supported=structured_output_supported,
    )


def agent_only(cases: list[BenchmarkCase]) -> list[BenchmarkCase]:
    """Keep only AGENT cases — VERIFIER_CHALLENGE cases test MEVA's verifier, not a model,
    and must never be used to compare models (see docs/model-comparison.md)."""
    return [c for c in cases if c.case_type == "AGENT"]


def run_model_comparison(
    model_names: list[str],
    cases: list[BenchmarkCase],
    benchmark_version: str,
    base_url: str | None = None,
    pause_between_cases: float = 0,
    pause_between_models: float = 0,
) -> list[ModelComparisonResult]:
    """Run every model over the exact same AGENT cases, sequentially.

    VERIFIER_CHALLENGE cases test MEVA's verifier, not a model (see
    docs/model-comparison.md), so they're filtered out here defensively
    even though the caller should already only pass AGENT cases. One
    model's failure (e.g. not installed, or fails the compatibility
    check) never corrupts another model's result.
    """
    cases = agent_only(cases)
    results = []

    for i, model_name in enumerate(model_names):
        if i > 0 and pause_between_models > 0:
            time.sleep(pause_between_models)

        try:
            base_config = get_model_config(model_name)
            config = describe_model(base_config, base_url=base_url)
        except ModelNotInstalledError as e:
            results.append(ModelComparisonResult(
                model=model_name, ollama_tag=model_name, provider="ollama-local",
                effective_configuration={},
                compatibility=CompatibilityResult(
                    model=model_name, tool_call_supported=False, structured_output_supported=False,
                    compatibility_error=str(e),
                ),
                benchmark_version=benchmark_version, agent_case_count=0, agent_metrics={},
            ))
            continue

        overrides = effective_agent_overrides(config)
        compatibility = check_compatibility(config, base_url=base_url)

        if not (compatibility.tool_call_supported and compatibility.structured_output_supported):
            results.append(ModelComparisonResult(
                model=config.name, ollama_tag=config.ollama_tag, provider=config.provider,
                digest=config.digest, parameter_size=config.parameter_size, quantization=config.quantization,
                capabilities=config.capabilities, license_name=config.license_name,
                effective_configuration=overrides, compatibility=compatibility,
                benchmark_version=benchmark_version, agent_case_count=0, agent_metrics={},
            ))
            unload_model(config.ollama_tag, base_url=base_url)
            continue

        case_results = run_benchmark(
            cases, model=config.ollama_tag, base_url=base_url,
            agent_overrides=overrides, pause_between_cases=pause_between_cases,
        )
        agent_metrics = aggregate_metrics(case_results)["agent"]

        results.append(ModelComparisonResult(
            model=config.name, ollama_tag=config.ollama_tag, provider=config.provider,
            digest=config.digest, parameter_size=config.parameter_size, quantization=config.quantization,
            capabilities=config.capabilities, license_name=config.license_name,
            effective_configuration=overrides, compatibility=compatibility,
            benchmark_version=benchmark_version, agent_case_count=len(cases),
            agent_metrics=agent_metrics, case_results=case_results,
        ))

        unload_model(config.ollama_tag, base_url=base_url)

    return results


def _hardware_note() -> str:
    """A generic, non-identifying OS/architecture string — never a hostname or username."""
    return f"{platform.system()} {platform.machine()}"


def build_comparison_payload(results: list[ModelComparisonResult], base_url: str | None = None) -> dict:
    """Assemble the full JSON-serializable comparison report (without writing it)."""
    return {
        "meva_version": MEVA_VERSION,
        "ollama_version": get_ollama_version(base_url),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hardware_note": _hardware_note(),
        "models": [r.model_dump() for r in results],
    }


def save_comparison_results(
    results: list[ModelComparisonResult], results_dir: str | Path | None = None, benchmark_version: str = "",
    base_url: str | None = None,
) -> Path:
    """Write a comparison report to results/comparisons/comparison-<version>-YYYYMMDD-HHMMSS.json."""
    directory = Path(results_dir) if results_dir else DEFAULT_COMPARISON_RESULTS_DIR
    directory.mkdir(parents=True, exist_ok=True)

    suffix = f"-{benchmark_version}" if benchmark_version else ""
    filename = f"comparison{suffix}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    output_path = directory / filename

    payload = build_comparison_payload(results, base_url=base_url)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    return output_path


# ==========================================================================
# Stage 7C2: full v0.3 AGENT-case comparison, resumable, with a once-only
# verifier-challenge run kept entirely separate from model performance.
# ==========================================================================


def run_full_comparison(
    model_names: list[str],
    agent_cases: list[BenchmarkCase],
    verifier_cases: list[BenchmarkCase],
    benchmark_version: str,
    run_id: str,
    base_url: str | None = None,
    pause_between_cases: float = 0,
    pause_between_models: float = 0,
    runs_dir: str | Path | None = None,
) -> tuple[list[ModelComparisonResult], list[BenchmarkResult]]:
    """Run every model over the full agent_cases list, resumably, and run
    verifier_cases exactly once (never per model — see docs/model-comparison.md).

    Progress is persisted to results/comparisons/runs/<run_id>.json after every
    completed case, so a killed/crashed process can resume with the same
    `run_id` and skip everything already done. Resuming with a different
    benchmark_version/model list/case list raises IncompatibleResumeError
    (via RunState.load_or_create) rather than silently mixing runs.

    Returns (model comparison results, verifier-challenge results).
    """
    agent_cases = agent_only(agent_cases)
    case_ids = [c.case_id for c in agent_cases]

    state = RunState.load_or_create(run_id, benchmark_version, model_names, case_ids, runs_dir=runs_dir)

    if state.verifier_challenge_results is None:
        verifier_results = run_benchmark(verifier_cases) if verifier_cases else []
        state.record_verifier_challenge_results([r.model_dump() for r in verifier_results])
    else:
        verifier_results = [BenchmarkResult(**d) for d in state.verifier_challenge_results]

    results = []

    for i, model_name in enumerate(model_names):
        cached = state.model_metadata.get(model_name)
        if cached and cached.get("comparison_result") and not cached.get("resume_case_run"):
            # A prior run already fully resolved this model as incompatible/not-installed —
            # reuse that result rather than re-probing every resume.
            results.append(ModelComparisonResult(**cached["comparison_result"]))
            continue

        if i > 0 and pause_between_models > 0:
            time.sleep(pause_between_models)

        try:
            base_config = get_model_config(model_name)
            config = describe_model(base_config, base_url=base_url)
        except ModelNotInstalledError as e:
            result = ModelComparisonResult(
                model=model_name, ollama_tag=model_name, provider="ollama-local",
                effective_configuration={},
                compatibility=CompatibilityResult(
                    model=model_name, tool_call_supported=False, structured_output_supported=False,
                    compatibility_error=str(e),
                ),
                benchmark_version=benchmark_version, agent_case_count=0, agent_metrics={},
            )
            results.append(result)
            state.record_model_metadata(model_name, {"comparison_result": result.model_dump()})
            continue

        overrides = effective_agent_overrides(config)
        already_started = any(state.is_case_done(model_name, cid) for cid in case_ids)

        if already_started:
            # Compatibility was already proven by the cases that completed before the resume.
            compatibility = CompatibilityResult(model=config.name, tool_call_supported=True, structured_output_supported=True)
        else:
            compatibility = check_compatibility(config, base_url=base_url)
            if not (compatibility.tool_call_supported and compatibility.structured_output_supported):
                result = ModelComparisonResult(
                    model=config.name, ollama_tag=config.ollama_tag, provider=config.provider,
                    digest=config.digest, parameter_size=config.parameter_size, quantization=config.quantization,
                    capabilities=config.capabilities, license_name=config.license_name,
                    effective_configuration=overrides, compatibility=compatibility,
                    benchmark_version=benchmark_version, agent_case_count=0, agent_metrics={},
                )
                results.append(result)
                state.record_model_metadata(model_name, {"comparison_result": result.model_dump()})
                unload_model(config.ollama_tag, base_url=base_url)
                continue

        skip_ids = {cid for cid in case_ids if state.is_case_done(model_name, cid)}

        def _on_case_complete(case_id: str, case_result: BenchmarkResult, _model_name: str = model_name) -> None:
            state.record_case_result(_model_name, case_id, case_result.model_dump())

        run_benchmark(
            agent_cases, model=config.ollama_tag, base_url=base_url,
            agent_overrides=overrides, pause_between_cases=pause_between_cases,
            skip_case_ids=skip_ids, on_case_complete=_on_case_complete,
        )

        case_results = [BenchmarkResult(**d) for d in state.case_results_for(model_name)]
        agent_metrics = aggregate_metrics(case_results)["agent"]

        result = ModelComparisonResult(
            model=config.name, ollama_tag=config.ollama_tag, provider=config.provider,
            digest=config.digest, parameter_size=config.parameter_size, quantization=config.quantization,
            capabilities=config.capabilities, license_name=config.license_name,
            effective_configuration=overrides, compatibility=compatibility,
            benchmark_version=benchmark_version, agent_case_count=len(agent_cases),
            agent_metrics=agent_metrics, case_results=case_results,
        )
        results.append(result)
        # `resume_case_run` marks this as a per-case run (not a static incompatible
        # verdict) so a *later* resume still re-derives agent_metrics from case_results
        # rather than reusing a stale cached ModelComparisonResult forever.
        state.record_model_metadata(model_name, {"comparison_result": result.model_dump(), "resume_case_run": True})

        unload_model(config.ollama_tag, base_url=base_url)

    return results, verifier_results


def generate_interpretation_warnings(results: list[ModelComparisonResult]) -> list[str]:
    """Automatic, non-ranking warnings about how to read these numbers together.

    Never used to declare a "winner" — only to flag when one metric alone
    (e.g. Evidence Grounding Score) would be misleading without another
    (e.g. Verifiable Claim Coverage) alongside it.
    """
    warnings = [
        "Evidence Grounding Score should be interpreted together with Verifiable Claim Coverage — "
        "a high grounding score over very few verifiable claims can look better than it is.",
        "Do not rank models by grounding score alone; retrieval, structured-output, and grounding "
        "are three separate layers that are never combined into one score.",
    ]
    for r in results:
        m = r.agent_metrics or {}
        coverage = m.get("verifiable_claim_coverage")
        grounding = m.get("evidence_grounding_score")
        if coverage is not None and coverage < 0.5 and grounding not in (None, "N/A"):
            warnings.append(
                f"{r.model}: grounding score is {grounding}, but verifiable_claim_coverage is only "
                f"{coverage:.2f} — most of this model's emitted claims were not verifiable at all, "
                f"so the grounding score alone overstates how much of its output was actually checked."
            )
    return warnings


def _read_manifest(benchmark_version: str) -> dict | None:
    manifest_path = (
        Path(__file__).resolve().parent.parent.parent.parent / "benchmarks" / benchmark_version / "manifest.json"
    )
    if not manifest_path.exists():
        return None
    with manifest_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_full_comparison_payload(
    model_results: list[ModelComparisonResult],
    verifier_results: list[BenchmarkResult],
    case_ids: list[str],
    benchmark_version: str,
    base_url: str | None = None,
) -> dict:
    """Assemble the full JSON-serializable Stage 7C2 comparison report."""
    verifier_success = [r for r in verifier_results if r.expected_status_achieved]
    return {
        "meva_version": MEVA_VERSION,
        "benchmark_version": benchmark_version,
        "benchmark_manifest": _read_manifest(benchmark_version),
        "ollama_version": get_ollama_version(base_url),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hardware_note": _hardware_note(),
        "case_ids": case_ids,
        "models": [r.model_dump() for r in model_results],
        "verifier_challenge": {
            "verifier_challenge_cases": len(verifier_results),
            "verifier_challenge_success_rate": (
                len(verifier_success) / len(verifier_results) if verifier_results else None
            ),
            "results": [r.model_dump() for r in verifier_results],
        },
        "warnings": generate_interpretation_warnings(model_results),
    }


def _fmt(value) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def build_comparison_markdown(payload: dict) -> str:
    """A concise, human-readable Markdown report from a build_full_comparison_payload() dict."""
    lines = ["# MEVA Model Comparison — Full v0.3 AGENT Benchmark", ""]
    lines.append(
        "This compares tool use, structured-output quality, and evidence grounding only. "
        "It is **not** a clinical safety, medical accuracy, or diagnostic-accuracy comparison."
    )
    lines.append("")
    lines.append(f"- MEVA version: `{payload['meva_version']}`")
    lines.append(f"- Benchmark version: `{payload['benchmark_version']}`")
    lines.append(f"- Ollama version: `{payload.get('ollama_version')}`")
    lines.append(f"- Hardware: {payload.get('hardware_note')}")
    lines.append(f"- Timestamp: {payload['timestamp']}")
    lines.append(f"- AGENT cases: {len(payload['case_ids'])}")
    lines.append("")

    models = [m for m in payload["models"] if m.get("agent_case_count", 0) > 0]
    if models:
        rows = [
            ("AGENT cases", lambda m: m["agent_case_count"]),
            ("Tool recall", lambda m: _fmt(m["agent_metrics"].get("tool_recall"))),
            ("Tool precision", lambda m: _fmt(m["agent_metrics"].get("tool_precision"))),
            ("Exact tool match", lambda m: _fmt(m["agent_metrics"].get("exact_tool_match_rate"))),
            ("Evidence recall", lambda m: _fmt(m["agent_metrics"].get("evidence_recall"))),
            ("Structured validity", lambda m: _fmt(m["agent_metrics"].get("structured_claim_validity_rate"))),
            ("Verifiable coverage", lambda m: _fmt(m["agent_metrics"].get("verifiable_claim_coverage"))),
            ("Mean case coverage*", lambda m: _fmt(m["agent_metrics"].get("mean_case_verifiable_coverage"))),
            ("Zero-claim rate", lambda m: _fmt(m["agent_metrics"].get("zero_claim_rate"))),
            ("Grounding score", lambda m: m["agent_metrics"].get("evidence_grounding_score")),
            ("Supported", lambda m: m["agent_metrics"].get("supported_claims")),
            ("Contradicted", lambda m: m["agent_metrics"].get("contradicted_claims")),
            ("Unsupported", lambda m: m["agent_metrics"].get("unsupported_claims")),
            ("Unverifiable", lambda m: m["agent_metrics"].get("unverifiable_claims")),
            ("Retrieval failures", lambda m: m["agent_metrics"].get("retrieval_failure_cases")),
            ("Structured failures", lambda m: m["agent_metrics"].get("structured_output_failure_cases")),
            ("Grounding failures", lambda m: m["agent_metrics"].get("grounding_failure_cases")),
            ("Successful cases", lambda m: m["agent_metrics"].get("successful_cases")),
            ("Median latency (s)", lambda m: _fmt(m["agent_metrics"].get("median_total_latency_seconds"))),
        ]
        header = "| Metric | " + " | ".join(m["model"] for m in models) + " |"
        sep = "|---" * (len(models) + 1) + "|"
        lines.append(header)
        lines.append(sep)
        for label, getter in rows:
            lines.append(f"| {label} | " + " | ".join(str(getter(m)) for m in models) + " |")
        lines.append("")
        lines.append(
            "Note: outcome-flag percentages (retrieval/structured/grounding failure, successful) are "
            "non-exclusive — a case can carry more than one flag, so counts need not sum to the case total."
        )
        lines.append(
            "\\* Mean case coverage is a secondary, distinctly-named metric (the unweighted mean of each "
            "case's own coverage, among cases with at least one claim) — it is NOT Verifiable Claim Coverage "
            "(the documented micro-average of totals) and must never be reported under that name."
        )
        lines.append("")

    incompatible = [m for m in payload["models"] if m.get("agent_case_count", 0) == 0]
    if incompatible:
        lines.append("## Excluded models")
        for m in incompatible:
            lines.append(f"- **{m['model']}**: {m['compatibility'].get('compatibility_error') or 'compatibility check failed'}")
        lines.append("")

    vc = payload["verifier_challenge"]
    lines.append("## Verifier challenge suite (run once, not per model)")
    lines.append(f"- Cases: {vc['verifier_challenge_cases']}")
    lines.append(f"- Success rate: {_fmt(vc['verifier_challenge_success_rate'])}")
    lines.append("")

    if payload.get("warnings"):
        lines.append("## Interpretation warnings")
        for w in payload["warnings"]:
            lines.append(f"- {w}")
        lines.append("")

    return "\n".join(lines) + "\n"


def save_full_comparison_results(
    model_results: list[ModelComparisonResult],
    verifier_results: list[BenchmarkResult],
    case_ids: list[str],
    benchmark_version: str,
    results_dir: str | Path | None = None,
    base_url: str | None = None,
) -> tuple[Path, Path]:
    """Write both the JSON and Markdown Stage 7C2 comparison reports. Returns (json_path, md_path)."""
    directory = Path(results_dir) if results_dir else DEFAULT_COMPARISON_RESULTS_DIR
    directory.mkdir(parents=True, exist_ok=True)

    payload = build_full_comparison_payload(model_results, verifier_results, case_ids, benchmark_version, base_url=base_url)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = directory / f"comparison-{benchmark_version}-full-{stamp}.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    md_path = directory / f"comparison-{benchmark_version}-full-{stamp}.md"
    md_path.write_text(build_comparison_markdown(payload), encoding="utf-8")

    return json_path, md_path


# ==========================================================================
# Stage 7C2.1: safe report regeneration from an already-saved raw run.
#
# Recomputes every aggregate (agent_metrics, warnings) from the saved
# per-case case_results using the CURRENT metrics formulas — without
# touching Ollama, without re-running any case, and without modifying the
# original historical file. Written for exactly the situation that
# motivated it: a metrics bug found after a completed run, where the raw
# per-case data was correct all along and only the aggregation was wrong.
# ==========================================================================


def regenerate_report(source_json_path: str | Path, results_dir: str | Path | None = None) -> tuple[Path, Path]:
    """Recompute a saved comparison report's aggregates from its own per-case results.

    Reads `source_json_path` (untouched, never overwritten), rebuilds each
    model's `agent_metrics` from its `case_results` with the current
    `aggregate_metrics()` formulas, regenerates `warnings`, and writes a new
    JSON + Markdown pair alongside the source with a `-corrected` suffix.
    `case_results` (the raw per-case data) and everything else in the
    original payload are carried through unchanged.
    """
    source_path = Path(source_json_path)
    with source_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    corrected_models: list[ModelComparisonResult] = []
    for model_data in payload["models"]:
        case_results = [BenchmarkResult(**cr) for cr in model_data.get("case_results", [])]
        if case_results:
            model_data = dict(model_data)
            model_data["agent_metrics"] = aggregate_metrics(case_results)["agent"]
        corrected_models.append(ModelComparisonResult(**model_data))

    verifier_results = [BenchmarkResult(**r) for r in payload.get("verifier_challenge", {}).get("results", [])]
    case_ids = payload.get("case_ids", [])
    benchmark_version = payload.get("benchmark_version", "")

    corrected_payload = build_full_comparison_payload(
        corrected_models, verifier_results, case_ids, benchmark_version,
    )
    # Preserve the original run's real ollama_version/timestamp provenance rather than
    # implying this was a fresh live run — this is a recompute, not a re-execution.
    corrected_payload["ollama_version"] = payload.get("ollama_version")
    corrected_payload["hardware_note"] = payload.get("hardware_note")
    corrected_payload["source_report"] = source_path.name
    corrected_payload["regenerated_at"] = datetime.now(timezone.utc).isoformat()
    corrected_payload["meva_version"] = payload.get("meva_version", MEVA_VERSION)
    corrected_payload["benchmark_manifest"] = payload.get("benchmark_manifest")

    directory = Path(results_dir) if results_dir else source_path.parent
    directory.mkdir(parents=True, exist_ok=True)
    stem = source_path.stem
    json_path = directory / f"{stem}-corrected.json"
    md_path = directory / f"{stem}-corrected.md"

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(corrected_payload, f, indent=2)
    md_path.write_text(build_comparison_markdown(corrected_payload), encoding="utf-8")

    return json_path, md_path
