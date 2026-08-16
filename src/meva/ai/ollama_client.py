"""A minimal client for a locally running Ollama server.

No API key is used or required — Ollama runs entirely on your own
machine. Configure it with environment variables if you want, but the
defaults work out of the box for a normal local Ollama install:

- MEVA_OLLAMA_URL   default: http://localhost:11434
- MEVA_MODEL        default: qwen3:4b

For reproducible/benchmarkable runs, MEVA's "evaluation mode" defaults
are temperature=0 and seed=42 (see docs/reproducibility.md). These are
applied by the agent, not hardcoded here — this client just knows how
to pass them through to Ollama.
"""

import json
import os
import urllib.error
import urllib.request

from pydantic import BaseModel

DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen3:4b"

# Ollama's reported metric field names, in the order MEVA reports them.
_METRIC_FIELDS = (
    "total_duration",
    "load_duration",
    "prompt_eval_count",
    "prompt_eval_duration",
    "eval_count",
    "eval_duration",
)


def base_url() -> str:
    return os.environ.get("MEVA_OLLAMA_URL", DEFAULT_BASE_URL)


def model_name() -> str:
    return os.environ.get("MEVA_MODEL", DEFAULT_MODEL)


class OllamaError(Exception):
    """Raised when the local Ollama server can't be reached or returns an error."""


class RunMetrics(BaseModel):
    """Timing/token metrics as actually reported by Ollama for one /api/chat call.

    Every field is optional and defaults to None — MEVA never invents a
    number Ollama didn't report. Durations are in nanoseconds, exactly
    as Ollama returns them.
    """

    total_duration: int | None = None
    load_duration: int | None = None
    prompt_eval_count: int | None = None
    prompt_eval_duration: int | None = None
    eval_count: int | None = None
    eval_duration: int | None = None

    @classmethod
    def from_response(cls, body: dict) -> "RunMetrics":
        return cls(**{field: body.get(field) for field in _METRIC_FIELDS})

    @property
    def total_seconds(self) -> float | None:
        return self.total_duration / 1e9 if self.total_duration is not None else None


class ChatResponse(BaseModel):
    """One /api/chat call's result: the assistant message plus its reported metrics."""

    message: dict
    metrics: RunMetrics


class OllamaClient:
    """Talks to the local Ollama /api/chat endpoint."""

    def __init__(self, base_url: str | None = None, model: str | None = None):
        self.base_url = (base_url or globals()["base_url"]()).rstrip("/")
        self.model = model or model_name()

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        format: dict | None = None,
        think: bool | None = None,
        temperature: float | None = None,
        seed: int | None = None,
        keep_alive: str | None = None,
    ) -> ChatResponse:
        """Send a chat request and return the assistant's message plus run metrics.

        `format` is an optional JSON schema (Ollama's structured output
        support) that constrains the shape of the response's content.
        `think`, `temperature`, `seed`, and `keep_alive` are all optional
        generation controls — omit any of them to use Ollama's own
        defaults for this model.

        Raises OllamaError if the local server can't be reached (e.g. it
        isn't running, or the model isn't pulled).
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
        if format:
            payload["format"] = format
        if think is not None:
            payload["think"] = think
        if keep_alive is not None:
            payload["keep_alive"] = keep_alive

        options = {}
        if temperature is not None:
            options["temperature"] = temperature
        if seed is not None:
            options["seed"] = seed
        if options:
            payload["options"] = options

        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise OllamaError(
                f"Could not reach Ollama at {self.base_url}. "
                f"Is it running? Try: ollama serve (or just `ollama list`). Details: {e.reason}"
            ) from None

        if "error" in body:
            raise OllamaError(body["error"])

        return ChatResponse(message=body["message"], metrics=RunMetrics.from_response(body))
