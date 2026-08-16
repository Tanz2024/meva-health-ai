"""Tests for MEVA's multi-model comparison layer.

Fully offline — meva.ai.agent.run_agent and meva.models.discovery calls
are all mocked. No Ollama required.
"""

import json
from unittest.mock import patch

from meva.ai.ollama_client import RunMetrics
from meva.benchmark import comparison
from meva.benchmark.models import BenchmarkCase
from meva.models.config import ModelConfig
from meva.models.discovery import ModelNotInstalledError

RICH_PATIENT_ID = "080b069b-5108-46b6-ecef-6aacd3b9ef3f"


def fake_agent_result(tool: str, result, answer: str, claims: list[dict], schema_parsed: bool = True):
    from meva.verification.models import MedicalClaim

    return {
        "answer": answer,
        "claims": [MedicalClaim(**c) for c in claims],
        "log": [{"model": "fake", "question": "q", "tool": tool, "arguments": {}, "result": result, "error": None}] if tool else [],
        "metrics": {
            "tool_calls": [RunMetrics(total_duration=1_000_000_000)],
            "final": RunMetrics(total_duration=500_000_000),
        },
        "claim_quality": {"schema_parsed": schema_parsed, "total_raw_claims": len(claims), "valid_claims": len(claims),
                           "structured_claim_validity_rate": 1.0 if claims else None},
    }


def fake_describe_model(config: ModelConfig, base_url=None) -> ModelConfig:
    updated = config.model_copy(update={
        "digest": "abc123", "parameter_size": "4.0B", "quantization": "Q4_K_M",
        "capabilities": ["completion", "tools", "thinking"], "license_name": "Apache License",
    })
    return updated


# --- compatibility check ------------------------------------------------

def test_compatibility_check_success():
    config = ModelConfig(name="qwen3:4b", ollama_tag="qwen3:4b")
    fake = fake_agent_result("get_allergies", [{"name": "Fish (substance)", "id": "x"}], "Fish allergy.",
                              [{"text": "t", "patient_id": RICH_PATIENT_ID, "category": "allergy", "value": "Fish", "assertion": "present"}])
    with patch("meva.benchmark.comparison.run_agent_fn", return_value=fake):
        result = comparison.check_compatibility(config)

    assert result.tool_call_supported is True
    assert result.structured_output_supported is True
    assert result.compatibility_error is None


def test_compatibility_check_failure_captured():
    config = ModelConfig(name="broken:1b", ollama_tag="broken:1b")
    with patch("meva.benchmark.comparison.run_agent_fn", side_effect=RuntimeError("connection refused")):
        result = comparison.check_compatibility(config)

    assert result.tool_call_supported is False
    assert result.structured_output_supported is False
    assert "connection refused" in result.compatibility_error


def test_compatibility_check_detects_malformed_schema():
    config = ModelConfig(name="qwen3:4b", ollama_tag="qwen3:4b")
    fake = fake_agent_result("get_allergies", [], "some text", [], schema_parsed=False)
    with patch("meva.benchmark.comparison.run_agent_fn", return_value=fake):
        result = comparison.check_compatibility(config)

    assert result.tool_call_supported is True
    assert result.structured_output_supported is False


# --- missing model / unsupported capability -----------------------------

def test_missing_model_handled_without_crashing():
    case = BenchmarkCase(case_id="c1", category="allergy", patient_id=RICH_PATIENT_ID, question="q", expected_tools=["get_allergies"], description="d")

    with patch("meva.benchmark.comparison.describe_model", side_effect=ModelNotInstalledError("Run: ollama pull missing:1b")):
        results = comparison.run_model_comparison(["qwen3:4b"], [case], benchmark_version="v0.3")

    assert len(results) == 1
    assert results[0].agent_case_count == 0
    assert "ollama pull" in results[0].compatibility.compatibility_error


def test_unsupported_capability_downgrades_think():
    from meva.models.discovery import describe_model

    config = ModelConfig(name="llama3.2:3b", ollama_tag="llama3.2:3b")
    show_response = {"capabilities": ["completion", "tools"], "details": {"parameter_size": "3.2B", "quantization_level": "Q4_K_M"}, "license": "LLAMA LICENSE\n..."}
    tags_response = [{"name": "llama3.2:3b", "digest": "xyz"}]

    with patch("meva.models.discovery.list_installed_models", return_value=tags_response), \
         patch("meva.models.discovery.fetch_model_show", return_value=show_response):
        updated = describe_model(config)

    assert updated.tool_think is False
    assert updated.structured_think is False
    assert updated.capabilities == ["completion", "tools"]


# --- same cases across models / result separation --------------------------

def test_same_case_list_used_across_models():
    cases = [
        BenchmarkCase(case_id="c1", category="allergy", patient_id=RICH_PATIENT_ID, question="q1", expected_tools=["get_allergies"], description="d"),
        BenchmarkCase(case_id="c2", category="medication", patient_id=RICH_PATIENT_ID, question="q2", expected_tools=["get_medications"], description="d"),
    ]
    fake = fake_agent_result("get_allergies", [{"name": "Fish (substance)", "id": "x"}], "ok",
                              [{"text": "t", "patient_id": RICH_PATIENT_ID, "category": "allergy", "value": "Fish", "assertion": "present"}])

    with patch("meva.benchmark.comparison.describe_model", side_effect=fake_describe_model), \
         patch("meva.benchmark.comparison.check_compatibility", return_value=comparison.CompatibilityResult(model="x", tool_call_supported=True, structured_output_supported=True)), \
         patch("meva.benchmark.graph.run_agent_fn", return_value=fake), \
         patch("meva.benchmark.comparison.unload_model", return_value=True):
        results = comparison.run_model_comparison(["qwen3:4b", "llama3.2:3b"], cases, benchmark_version="v0.3", pause_between_models=0)

    assert len(results) == 2
    for r in results:
        assert [c.case_id for c in r.case_results] == ["c1", "c2"]
    assert results[0].model == "qwen3:4b"
    assert results[1].model == "llama3.2:3b"


def test_verifier_challenge_cases_excluded_from_model_comparison():
    agent_case = BenchmarkCase(case_id="a1", category="allergy", patient_id=RICH_PATIENT_ID, question="q", expected_tools=["get_allergies"], description="d")
    challenge_case = BenchmarkCase(
        case_id="v1", category="verifier_challenge", case_type="VERIFIER_CHALLENGE", patient_id=RICH_PATIENT_ID,
        question="q", expected_tools=[], description="d",
        injected_claim={"text": "x", "patient_id": RICH_PATIENT_ID, "category": "allergy", "value": None, "assertion": "absent"},
    )
    assert comparison.agent_only([agent_case, challenge_case]) == [agent_case]


# --- retrieval / structured / grounding metrics preserved -------------------

def test_retrieval_structured_grounding_metrics_all_present():
    case = BenchmarkCase(case_id="c1", category="allergy", patient_id=RICH_PATIENT_ID, question="q", expected_tools=["get_allergies"], description="d")
    fake = fake_agent_result("get_allergies", [{"name": "Fish (substance)", "id": "x"}], "ok",
                              [{"text": "t", "patient_id": RICH_PATIENT_ID, "category": "allergy", "value": "Fish", "assertion": "present"}])

    with patch("meva.benchmark.comparison.describe_model", side_effect=fake_describe_model), \
         patch("meva.benchmark.comparison.check_compatibility", return_value=comparison.CompatibilityResult(model="x", tool_call_supported=True, structured_output_supported=True)), \
         patch("meva.benchmark.graph.run_agent_fn", return_value=fake), \
         patch("meva.benchmark.comparison.unload_model", return_value=True):
        results = comparison.run_model_comparison(["qwen3:4b"], [case], benchmark_version="v0.3")

    metrics = results[0].agent_metrics
    # retrieval
    assert "tool_recall" in metrics and "tool_precision" in metrics and "evidence_recall" in metrics
    # structured
    assert "structured_claim_validity_rate" in metrics
    # grounding
    assert "evidence_grounding_score" in metrics and "supported_claims" in metrics


# --- serialization -----------------------------------------------------

def test_comparison_serialization_round_trip(tmp_path):
    case = BenchmarkCase(case_id="c1", category="allergy", patient_id=RICH_PATIENT_ID, question="q", expected_tools=["get_allergies"], description="d")
    fake = fake_agent_result("get_allergies", [{"name": "Fish (substance)", "id": "x"}], "ok",
                              [{"text": "t", "patient_id": RICH_PATIENT_ID, "category": "allergy", "value": "Fish", "assertion": "present"}])

    with patch("meva.benchmark.comparison.describe_model", side_effect=fake_describe_model), \
         patch("meva.benchmark.comparison.check_compatibility", return_value=comparison.CompatibilityResult(model="x", tool_call_supported=True, structured_output_supported=True)), \
         patch("meva.benchmark.graph.run_agent_fn", return_value=fake), \
         patch("meva.benchmark.comparison.get_ollama_version", return_value="0.24.0"):
        results = comparison.run_model_comparison(["qwen3:4b"], [case], benchmark_version="v0.3")
        path = comparison.save_comparison_results(results, results_dir=tmp_path, benchmark_version="v0.3")

    assert path.exists()
    payload = json.loads(path.read_text())
    assert payload["ollama_version"] == "0.24.0"
    assert len(payload["models"]) == 1
    assert payload["models"][0]["digest"] == "abc123"


# --- one failing model doesn't corrupt the other -----------------------

def test_one_failing_model_does_not_corrupt_other_result():
    case = BenchmarkCase(case_id="c1", category="allergy", patient_id=RICH_PATIENT_ID, question="q", expected_tools=["get_allergies"], description="d")
    fake = fake_agent_result("get_allergies", [{"name": "Fish (substance)", "id": "x"}], "ok",
                              [{"text": "t", "patient_id": RICH_PATIENT_ID, "category": "allergy", "value": "Fish", "assertion": "present"}])

    def describe_side_effect(config, base_url=None):
        if config.name == "qwen3:4b":
            raise ModelNotInstalledError("Run: ollama pull qwen3:4b")
        return fake_describe_model(config, base_url)

    with patch("meva.benchmark.comparison.describe_model", side_effect=describe_side_effect), \
         patch("meva.benchmark.comparison.check_compatibility", return_value=comparison.CompatibilityResult(model="x", tool_call_supported=True, structured_output_supported=True)), \
         patch("meva.benchmark.graph.run_agent_fn", return_value=fake), \
         patch("meva.benchmark.comparison.unload_model", return_value=True):
        results = comparison.run_model_comparison(["qwen3:4b", "llama3.2:3b"], [case], benchmark_version="v0.3")

    assert results[0].agent_case_count == 0
    assert results[0].compatibility.compatibility_error is not None
    assert results[1].agent_case_count == 1
    assert results[1].agent_metrics["supported_claims"] == 1
