"""Tests for MEVA's local AI agent layer.

These tests never talk to a real Ollama server — the model's responses
are faked (mocked), so the tests run fully offline and don't need
Ollama installed or running.
"""

import json

import pytest

from meva.ai import agent, tools
from meva.ai.ollama_client import DEFAULT_BASE_URL, DEFAULT_MODEL, ChatResponse, RunMetrics

RICH_PATIENT_ID = "080b069b-5108-46b6-ecef-6aacd3b9ef3f"
SPARSE_PATIENT_ID = "d15b23ed-02d5-3e28-efbd-2604425317c5"


class FakeOllamaClient:
    """Stands in for OllamaClient: returns pre-scripted messages instead of calling a real server.

    Also records every call's kwargs, so tests can assert on what
    generation settings (think/temperature/seed/keep_alive) were sent.
    """

    def __init__(self, scripted_messages, base_url=None, model=None, metrics=None):
        self.model = model or DEFAULT_MODEL
        self._messages = list(scripted_messages)
        self._metrics = list(metrics) if metrics else None
        self.calls = 0
        self.call_kwargs = []

    def chat(self, messages, tools=None, format=None, think=None, temperature=None, seed=None, keep_alive=None):
        self.calls += 1
        self.call_kwargs.append({
            "tools": tools, "format": format, "think": think,
            "temperature": temperature, "seed": seed, "keep_alive": keep_alive,
        })
        message = self._messages.pop(0)
        metrics = self._metrics.pop(0) if self._metrics else RunMetrics()
        return ChatResponse(message=message, metrics=metrics)


def _install_fake_client(monkeypatch, scripted_messages, metrics=None):
    fake = FakeOllamaClient(scripted_messages, metrics=metrics)
    monkeypatch.setattr(agent, "OllamaClient", lambda base_url=None, model=None: fake)
    return fake


def tool_call_message(name: str, arguments: dict) -> dict:
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"function": {"name": name, "arguments": arguments}}],
    }


def final_message(text: str) -> dict:
    """A plain assistant message with no tool_calls — ends the tool-calling phase."""
    return {"role": "assistant", "content": text}


def structured_message(answer: str, claims: list[dict] | None = None) -> dict:
    """The model's final structured JSON response (answer + claims)."""
    return {"role": "assistant", "content": json.dumps({"answer": answer, "claims": claims or []})}


# --- tool dispatch -----------------------------------------------------

def test_correct_tool_dispatch(monkeypatch):
    scripted = [
        tool_call_message("get_patient", {"patient_id": RICH_PATIENT_ID}),
        final_message(""),
        structured_message(
            "Here is the patient info.",
            [{"text": "Patient is female", "patient_id": RICH_PATIENT_ID, "category": "patient", "value": "female", "assertion": "present"}],
        ),
    ]
    _install_fake_client(monkeypatch, scripted)

    result = agent.run_agent(f"Who is patient {RICH_PATIENT_ID}?")

    assert result["answer"] == "Here is the patient info."
    assert len(result["log"]) == 1
    assert result["log"][0]["tool"] == "get_patient"
    assert result["log"][0]["result"]["patient_id"] == RICH_PATIENT_ID
    assert result["log"][0]["error"] is None
    assert len(result["claims"]) == 1
    assert result["claims"][0].category == "patient"


def test_invalid_tool_rejected(monkeypatch):
    scripted = [
        tool_call_message("delete_everything", {}),
        final_message(""),
        structured_message("I can't do that."),
    ]
    _install_fake_client(monkeypatch, scripted)

    result = agent.run_agent("Delete all records.")

    assert result["log"][0]["tool"] == "delete_everything"
    assert result["log"][0]["error"] is not None
    assert "Unknown tool" in result["log"][0]["error"]


def test_invalid_patient_handled(monkeypatch):
    scripted = [
        tool_call_message("get_allergies", {"patient_id": "not-a-real-id"}),
        final_message(""),
        structured_message("I couldn't find that patient."),
    ]
    _install_fake_client(monkeypatch, scripted)

    result = agent.run_agent("Allergies for patient not-a-real-id?")

    assert result["log"][0]["error"] is not None
    assert "not-a-real-id" in result["log"][0]["error"]


def test_tool_arguments_validated_missing_patient_id():
    with pytest.raises(ValueError, match="missing required argument"):
        tools.call_tool("get_allergies", {})


def test_tool_arguments_validated_unknown_tool():
    with pytest.raises(ValueError, match="Unknown tool"):
        tools.call_tool("not_a_real_tool", {"patient_id": RICH_PATIENT_ID})


# --- round limit ---------------------------------------------------------

def test_maximum_tool_rounds_enforced(monkeypatch):
    # The model keeps asking for tools forever; agent must not loop infinitely.
    always_tool_calls = [tool_call_message("list_patients", {}) for _ in range(agent.MAX_TOOL_ROUNDS)]
    scripted = always_tool_calls + [structured_message("Giving up gracefully.")]
    fake = _install_fake_client(monkeypatch, scripted)

    result = agent.run_agent("Keep calling tools forever.")

    assert result["answer"] == "Giving up gracefully."
    assert fake.calls == agent.MAX_TOOL_ROUNDS + 1
    assert len(result["log"]) == agent.MAX_TOOL_ROUNDS


# --- empty evidence --------------------------------------------------------

def test_empty_evidence_handled_honestly(monkeypatch):
    scripted = [
        tool_call_message("get_allergies", {"patient_id": SPARSE_PATIENT_ID}),
        final_message(""),
        structured_message("No allergies are recorded for this patient."),
    ]
    _install_fake_client(monkeypatch, scripted)

    result = agent.run_agent(f"Allergies for patient {SPARSE_PATIENT_ID}?")

    assert result["log"][0]["result"] == []
    assert "no allergies" in result["answer"].lower()


def test_final_answer_returned_without_any_tool_call(monkeypatch):
    scripted = [
        final_message(""),
        structured_message("I need a patient_id to answer that."),
    ]
    _install_fake_client(monkeypatch, scripted)

    result = agent.run_agent("What allergies does the patient have?")

    assert result["answer"] == "I need a patient_id to answer that."
    assert result["log"] == []


def test_malformed_claim_is_dropped_not_crashed(monkeypatch):
    scripted = [
        final_message(""),
        # "category" is missing on the second claim — that one should be dropped, not crash the run.
        {"role": "assistant", "content": json.dumps({
            "answer": "Partial claims.",
            "claims": [
                {"text": "ok", "patient_id": RICH_PATIENT_ID, "category": "allergy", "value": "Fish", "assertion": "present"},
                {"text": "broken"},
            ],
        })},
    ]
    _install_fake_client(monkeypatch, scripted)

    result = agent.run_agent("Anything?")

    assert result["answer"] == "Partial claims."
    assert len(result["claims"]) == 1


# --- generation settings (Stage 6.5) ---------------------------------------

def test_think_false_sent_for_final_structured_call(monkeypatch):
    scripted = [final_message(""), structured_message("ok")]
    fake = _install_fake_client(monkeypatch, scripted)

    agent.run_agent("Anything?")

    assert fake.call_kwargs[-1]["think"] is agent.FINAL_STRUCTURED_THINK
    assert fake.call_kwargs[-1]["think"] is False


def test_think_true_sent_for_tool_call_phase_by_default(monkeypatch):
    scripted = [final_message(""), structured_message("ok")]
    fake = _install_fake_client(monkeypatch, scripted)

    agent.run_agent("Anything?")

    assert fake.call_kwargs[0]["think"] is agent.TOOL_CALL_THINK
    assert fake.call_kwargs[0]["think"] is True


def test_temperature_zero_sent_by_default(monkeypatch):
    scripted = [final_message(""), structured_message("ok")]
    fake = _install_fake_client(monkeypatch, scripted)

    agent.run_agent("Anything?")

    for call in fake.call_kwargs:
        assert call["temperature"] == 0


def test_seed_42_sent_by_default(monkeypatch):
    scripted = [final_message(""), structured_message("ok")]
    fake = _install_fake_client(monkeypatch, scripted)

    agent.run_agent("Anything?")

    for call in fake.call_kwargs:
        assert call["seed"] == 42


def test_generation_settings_are_overridable(monkeypatch):
    scripted = [final_message(""), structured_message("ok")]
    fake = _install_fake_client(monkeypatch, scripted)

    agent.run_agent("Anything?", temperature=0.7, seed=7, tool_call_think=False, final_structured_think=True)

    assert fake.call_kwargs[0]["temperature"] == 0.7
    assert fake.call_kwargs[0]["seed"] == 7
    assert fake.call_kwargs[0]["think"] is False
    assert fake.call_kwargs[-1]["think"] is True


# --- metrics -----------------------------------------------------------

def test_metrics_parsed_correctly():
    body = {
        "total_duration": 100,
        "load_duration": 10,
        "prompt_eval_count": 5,
        "prompt_eval_duration": 20,
        "eval_count": 30,
        "eval_duration": 70,
        "message": {"role": "assistant", "content": "hi"},
    }
    metrics = RunMetrics.from_response(body)
    assert metrics.total_duration == 100
    assert metrics.eval_count == 30
    assert metrics.total_seconds == 1e-7


def test_missing_metrics_handled_safely():
    metrics = RunMetrics.from_response({})
    assert metrics.total_duration is None
    assert metrics.eval_count is None
    assert metrics.total_seconds is None


def test_run_agent_returns_metrics(monkeypatch):
    metrics_sequence = [
        RunMetrics(total_duration=111, eval_count=1),
        RunMetrics(total_duration=222, eval_count=2),
    ]
    scripted = [final_message(""), structured_message("ok")]
    _install_fake_client(monkeypatch, scripted, metrics=metrics_sequence)

    result = agent.run_agent("Anything?")

    assert result["metrics"]["tool_calls"][0].total_duration == 111
    assert result["metrics"]["final"].total_duration == 222


# --- no paid API -----------------------------------------------------------

def test_no_paid_api_dependency_exists():
    from pathlib import Path

    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    text = pyproject.read_text().lower()
    for forbidden in ("openai", "anthropic", "google-generativeai"):
        assert forbidden not in text

    assert DEFAULT_BASE_URL == "http://localhost:11434"
    assert ":cloud" not in DEFAULT_MODEL
