"""Tests for MEVA's Stage 7C2 full-benchmark comparison: verifiable claim coverage,
zero-claim tracking, case-outcome taxonomy, grouped metrics, resumable execution,
and Markdown report generation. Fully offline — no Ollama required.
"""

from unittest.mock import patch

from meva.ai.ollama_client import RunMetrics
from meva.benchmark import comparison
from meva.benchmark.metrics import classify_case_outcome, grouped_agent_metrics, verifiable_claim_coverage
from meva.benchmark.models import BenchmarkCase, BenchmarkResult
from meva.benchmark.run_state import IncompatibleResumeError, RunState
from meva.models.config import ModelConfig

RICH_PATIENT_ID = "080b069b-5108-46b6-ecef-6aacd3b9ef3f"


def _result(**overrides) -> BenchmarkResult:
    base = dict(
        case_id="c1", category="allergy", case_type="AGENT", difficulty="simple",
        patient_id=RICH_PATIENT_ID, question="q", status="passed",
        required_tool_recall=1.0, tool_precision=1.0, exact_tool_match=True, evidence_recall=1.0,
        structured_claim_validity_rate=1.0, total_emitted_claims=1, zero_claim=False,
        supported=1, contradicted=0, unsupported=0, unverifiable=0,
    )
    base.update(overrides)
    return BenchmarkResult(**base)


# --- 1. verifiable claim coverage ---------------------------------------

def test_verifiable_claim_coverage_formula():
    assert verifiable_claim_coverage(2, 1, 1, 5) == 4 / 5
    assert verifiable_claim_coverage(0, 0, 0, 0) is None  # N/A when nothing was emitted
    assert verifiable_claim_coverage(0, 0, 3, 3) == 1.0  # unverifiable-free case: full coverage
    assert verifiable_claim_coverage(1, 0, 0, 4) == 0.25  # 3 unverifiable claims drag coverage down


# --- 2. zero-claim rate --------------------------------------------------

def test_zero_claim_rate_aggregation():
    results = [
        _result(case_id="a", zero_claim=False, total_emitted_claims=1),
        _result(case_id="b", zero_claim=True, total_emitted_claims=0, structured_claim_validity_rate=None),
    ]
    from meva.benchmark.metrics import _agent_metrics_summary
    summary = _agent_metrics_summary(results)
    assert summary["zero_claim_cases"] == 1
    assert summary["zero_claim_rate"] == 0.5


# --- 3-6. case outcome classification ------------------------------------

def test_retrieval_failure_classification():
    r = _result(required_tool_recall=0.5)
    flags = classify_case_outcome(r)
    assert flags["retrieval_failure"] is True
    assert flags["successful"] is False


def test_structured_output_failure_classification():
    r = _result(zero_claim=True, total_emitted_claims=0, structured_claim_validity_rate=None)
    flags = classify_case_outcome(r)
    assert flags["structured_output_failure"] is True
    assert flags["successful"] is False


def test_grounding_failure_classification():
    r = _result(supported=0, contradicted=1)
    flags = classify_case_outcome(r)
    assert flags["grounding_failure"] is True
    assert flags["successful"] is False


def test_overlapping_failure_flags():
    r = _result(required_tool_recall=0.5, zero_claim=True, total_emitted_claims=0,
                structured_claim_validity_rate=None, supported=0, contradicted=1)
    flags = classify_case_outcome(r)
    assert flags["retrieval_failure"] is True
    assert flags["structured_output_failure"] is True
    assert flags["grounding_failure"] is True
    assert flags["successful"] is False


def test_successful_case_classification():
    r = _result()
    flags = classify_case_outcome(r)
    assert flags == {"retrieval_failure": False, "structured_output_failure": False, "grounding_failure": False, "successful": True}


def test_verifier_challenge_and_error_cases_get_no_flags():
    challenge = _result(case_type="VERIFIER_CHALLENGE")
    errored = _result(status="error")
    assert classify_case_outcome(challenge)["successful"] is False
    assert classify_case_outcome(errored)["successful"] is False
    assert all(v is False for v in classify_case_outcome(challenge).values())


# --- 8-9. grouped metrics -------------------------------------------------

def test_grouped_category_metrics_include_n():
    results = [
        _result(case_id="a1", category="allergy"),
        _result(case_id="a2", category="allergy", supported=0, contradicted=1),
        _result(case_id="m1", category="medication"),
    ]
    grouped = grouped_agent_metrics(results, lambda r: r.category)
    assert grouped["allergy"]["n"] == 2
    assert grouped["medication"]["n"] == 1
    assert grouped["allergy"]["grounding_failure_cases"] == 1


def test_grouped_difficulty_metrics_include_n():
    results = [
        _result(case_id="a1", difficulty="simple"),
        _result(case_id="a2", difficulty="multi_tool"),
    ]
    grouped = grouped_agent_metrics(results, lambda r: r.difficulty)
    assert grouped["simple"]["n"] == 1
    assert grouped["multi_tool"]["n"] == 1


# --- 10-13. resume behavior ------------------------------------------------

def test_same_case_order_across_models(tmp_path):
    state = RunState.load_or_create("run1", "v0.3", ["qwen3:4b", "llama3.2:3b"], ["c1", "c2"], runs_dir=tmp_path)
    assert state.case_ids == ["c1", "c2"]
    assert state.models == ["qwen3:4b", "llama3.2:3b"]


def test_resume_saves_after_each_case(tmp_path):
    state = RunState.load_or_create("run1", "v0.3", ["qwen3:4b"], ["c1", "c2"], runs_dir=tmp_path)
    state.record_case_result("qwen3:4b", "c1", {"case_id": "c1"})
    assert (tmp_path / "run1.json").exists()

    reloaded = RunState.load_or_create("run1", "v0.3", ["qwen3:4b"], ["c1", "c2"], runs_dir=tmp_path)
    assert reloaded.is_case_done("qwen3:4b", "c1")
    assert not reloaded.is_case_done("qwen3:4b", "c2")


def test_resume_skips_completed_work(tmp_path):
    state = RunState.load_or_create("run1", "v0.3", ["qwen3:4b"], ["c1", "c2"], runs_dir=tmp_path)
    state.record_case_result("qwen3:4b", "c1", {"case_id": "c1"})

    reloaded = RunState.load_or_create("run1", "v0.3", ["qwen3:4b"], ["c1", "c2"], runs_dir=tmp_path)
    skip_ids = {cid for cid in reloaded.case_ids if reloaded.is_case_done("qwen3:4b", cid)}
    assert skip_ids == {"c1"}


def test_incompatible_resume_rejected(tmp_path):
    RunState.load_or_create("run1", "v0.3", ["qwen3:4b"], ["c1", "c2"], runs_dir=tmp_path)

    try:
        RunState.load_or_create("run1", "v0.3", ["qwen3:4b", "llama3.2:3b"], ["c1", "c2"], runs_dir=tmp_path)
        assert False, "expected IncompatibleResumeError"
    except IncompatibleResumeError:
        pass

    try:
        RunState.load_or_create("run1", "v0.4", ["qwen3:4b"], ["c1", "c2"], runs_dir=tmp_path)
        assert False, "expected IncompatibleResumeError"
    except IncompatibleResumeError:
        pass

    try:
        RunState.load_or_create("run1", "v0.3", ["qwen3:4b"], ["c1", "c3"], runs_dir=tmp_path)
        assert False, "expected IncompatibleResumeError"
    except IncompatibleResumeError:
        pass


# --- 14. one model failure isolated in full comparison ---------------------

def fake_agent_result(tool, result, answer, claims_raw, schema_parsed=True):
    from meva.verification.models import MedicalClaim
    return {
        "answer": answer,
        "claims": [MedicalClaim(**c) for c in claims_raw],
        "log": [{"model": "fake", "question": "q", "tool": tool, "arguments": {}, "result": result, "error": None}] if tool else [],
        "metrics": {"tool_calls": [RunMetrics(total_duration=1_000_000_000)], "final": RunMetrics(total_duration=500_000_000)},
        "claim_quality": {"schema_parsed": schema_parsed, "total_raw_claims": len(claims_raw), "valid_claims": len(claims_raw),
                           "structured_claim_validity_rate": 1.0 if claims_raw else None,
                           "malformed_attribute_claim_count": 0, "wrong_category_or_assertion_count": 0},
    }


def fake_describe_model(config: ModelConfig, base_url=None) -> ModelConfig:
    return config.model_copy(update={"digest": "abc123", "parameter_size": "4.0B", "quantization": "Q4_K_M",
                                      "capabilities": ["completion", "tools", "thinking"], "license_name": "Apache License"})


def test_one_model_failure_isolated_in_full_comparison(tmp_path):
    from meva.models.discovery import ModelNotInstalledError

    case = BenchmarkCase(case_id="c1", category="allergy", patient_id=RICH_PATIENT_ID, question="q",
                          expected_tools=["get_allergies"], description="d")
    fake = fake_agent_result("get_allergies", [{"name": "Fish (substance)", "id": "x"}], "ok",
                              [{"text": "t", "patient_id": RICH_PATIENT_ID, "category": "allergy", "value": "Fish", "assertion": "present"}])

    def describe_side_effect(config, base_url=None):
        if config.name == "llama3.2:3b":
            raise ModelNotInstalledError("Run: ollama pull llama3.2:3b")
        return fake_describe_model(config, base_url)

    with patch("meva.benchmark.comparison.describe_model", side_effect=describe_side_effect), \
         patch("meva.benchmark.comparison.check_compatibility", return_value=comparison.CompatibilityResult(model="x", tool_call_supported=True, structured_output_supported=True)), \
         patch("meva.benchmark.graph.run_agent_fn", return_value=fake), \
         patch("meva.benchmark.comparison.unload_model", return_value=True):
        model_results, verifier_results = comparison.run_full_comparison(
            ["llama3.2:3b", "qwen3:4b"], [case], [], benchmark_version="v0.3", run_id="isolation-test", runs_dir=tmp_path,
        )

    assert model_results[0].agent_case_count == 0
    assert model_results[0].compatibility.compatibility_error is not None
    assert model_results[1].agent_case_count == 1
    assert model_results[1].agent_metrics["supported_claims"] == 1


# --- 15. verifier challenges run once --------------------------------------

def test_verifier_challenges_run_once_not_per_model(tmp_path):
    agent_case = BenchmarkCase(case_id="c1", category="allergy", patient_id=RICH_PATIENT_ID, question="q",
                                expected_tools=["get_allergies"], description="d")
    challenge = BenchmarkCase(
        case_id="v1", category="verifier_challenge", case_type="VERIFIER_CHALLENGE", patient_id=RICH_PATIENT_ID,
        question="q", expected_tools=[], description="d",
        injected_claim={"text": "x", "patient_id": RICH_PATIENT_ID, "category": "allergy", "value": None, "assertion": "absent"},
    )
    fake = fake_agent_result("get_allergies", [{"name": "Fish (substance)", "id": "x"}], "ok",
                              [{"text": "t", "patient_id": RICH_PATIENT_ID, "category": "allergy", "value": "Fish", "assertion": "present"}])

    call_count = {"n": 0}

    def counting_run_benchmark(cases, **kwargs):
        for c in cases:
            if c.case_type == "VERIFIER_CHALLENGE":
                call_count["n"] += 1
        from meva.benchmark.runner import run_benchmark as real_run_benchmark
        return real_run_benchmark(cases, **kwargs)

    with patch("meva.benchmark.comparison.describe_model", side_effect=fake_describe_model), \
         patch("meva.benchmark.comparison.check_compatibility", return_value=comparison.CompatibilityResult(model="x", tool_call_supported=True, structured_output_supported=True)), \
         patch("meva.benchmark.graph.run_agent_fn", return_value=fake), \
         patch("meva.benchmark.comparison.unload_model", return_value=True), \
         patch("meva.benchmark.comparison.run_benchmark", side_effect=counting_run_benchmark):
        model_results, verifier_results = comparison.run_full_comparison(
            ["qwen3:4b", "llama3.2:3b"], [agent_case], [challenge], benchmark_version="v0.3",
            run_id="verifier-once-test", runs_dir=tmp_path,
        )

    assert call_count["n"] == 1  # the challenge case only ever ran once, not once per model
    assert len(verifier_results) == 1
    assert verifier_results[0].case_type == "VERIFIER_CHALLENGE"


# --- 16. markdown report generation -----------------------------------------

def test_markdown_report_generation(tmp_path):
    case = BenchmarkCase(case_id="c1", category="allergy", patient_id=RICH_PATIENT_ID, question="q",
                          expected_tools=["get_allergies"], description="d")
    fake = fake_agent_result("get_allergies", [{"name": "Fish (substance)", "id": "x"}], "ok",
                              [{"text": "t", "patient_id": RICH_PATIENT_ID, "category": "allergy", "value": "Fish", "assertion": "present"}])

    with patch("meva.benchmark.comparison.describe_model", side_effect=fake_describe_model), \
         patch("meva.benchmark.comparison.check_compatibility", return_value=comparison.CompatibilityResult(model="x", tool_call_supported=True, structured_output_supported=True)), \
         patch("meva.benchmark.graph.run_agent_fn", return_value=fake), \
         patch("meva.benchmark.comparison.unload_model", return_value=True), \
         patch("meva.benchmark.comparison.get_ollama_version", return_value="0.24.0"):
        model_results, verifier_results = comparison.run_full_comparison(
            ["qwen3:4b"], [case], [], benchmark_version="v0.3", run_id="md-test", runs_dir=tmp_path,
        )
        json_path, md_path = comparison.save_full_comparison_results(
            model_results, verifier_results, [case.case_id], benchmark_version="v0.3", results_dir=tmp_path,
        )

    assert json_path.exists()
    assert md_path.exists()
    text = md_path.read_text()
    assert "MEVA Model Comparison" in text
    assert "qwen3:4b" in text
    assert "clinical safety" in text.lower()
