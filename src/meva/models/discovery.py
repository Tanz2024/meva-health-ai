"""Query the local Ollama server for real model metadata and installation status.

Nothing here is guessed or hardcoded — every field comes from Ollama's
own `/api/tags` and `/api/show` responses. If a model isn't installed,
MEVA reports the exact `ollama pull <tag>` command and stops; it never
downloads a multi-GB model automatically.
"""

import json
import urllib.error
import urllib.request

from meva.ai.ollama_client import base_url as ollama_base_url
from meva.models.config import ModelConfig


class ModelNotInstalledError(Exception):
    """Raised when a registered model isn't installed locally. Message includes the pull command."""


def _get(url: str, timeout: int = 10) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _post(url: str, payload: dict, timeout: int = 30) -> dict:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def get_ollama_version(base_url: str | None = None) -> str | None:
    """GET /api/version — the running Ollama server's version, or None if unreachable."""
    url = f"{(base_url or ollama_base_url()).rstrip('/')}/api/version"
    try:
        return _get(url).get("version")
    except urllib.error.URLError:
        return None


def list_installed_models(base_url: str | None = None) -> list[dict]:
    """Raw entries from GET /api/tags: name, digest, size, details, ..."""
    url = f"{(base_url or ollama_base_url()).rstrip('/')}/api/tags"
    return _get(url).get("models", [])


def is_model_installed(tag: str, base_url: str | None = None) -> bool:
    return any(m.get("name") == tag for m in list_installed_models(base_url))


def fetch_model_show(tag: str, base_url: str | None = None) -> dict:
    """Raw response from POST /api/show for one model tag."""
    url = f"{(base_url or ollama_base_url()).rstrip('/')}/api/show"
    return _post(url, {"model": tag})


def describe_model(config: ModelConfig, base_url: str | None = None) -> ModelConfig:
    """Return a copy of `config` filled with real metadata from a live Ollama query.

    If the model isn't installed, raises ModelNotInstalledError with the
    exact pull command — never downloads it automatically. If the model
    doesn't report "thinking" among its capabilities, `tool_think` and
    `structured_think` are downgraded to False rather than sent anyway
    (Ollama itself rejects a `think` param on a non-thinking model).
    """
    try:
        installed = list_installed_models(base_url)
    except urllib.error.URLError as e:
        raise ModelNotInstalledError(f"Could not reach Ollama to check installed models: {e.reason}") from None

    match = next((m for m in installed if m.get("name") == config.ollama_tag), None)
    if match is None:
        raise ModelNotInstalledError(
            f"Model '{config.ollama_tag}' is not installed locally. Run: ollama pull {config.ollama_tag}"
        )

    show = fetch_model_show(config.ollama_tag, base_url)
    details = show.get("details") or {}
    capabilities = show.get("capabilities")
    license_text = show.get("license")
    license_name = license_text.splitlines()[0].strip() if license_text else None

    updated = config.model_copy(update={
        "digest": match.get("digest"),
        "parameter_size": details.get("parameter_size"),
        "quantization": details.get("quantization_level"),
        "capabilities": capabilities,
        "license_name": license_name,
    })

    if capabilities is not None and "thinking" not in capabilities:
        updated.tool_think = False
        updated.structured_think = False

    return updated


def think_supported(config: ModelConfig) -> bool:
    """Whether this model reported "thinking" among its Ollama capabilities."""
    return config.capabilities is not None and "thinking" in config.capabilities


def unload_model(tag: str, base_url: str | None = None) -> bool:
    """Ask Ollama to unload a model from memory now (keep_alive=0), where practical.

    Best-effort: returns True if the request succeeded, False if Ollama
    couldn't be reached. Never raises — an unload failure shouldn't stop
    a benchmark run, it just means the next model may take longer to load.
    """
    url = f"{(base_url or ollama_base_url()).rstrip('/')}/api/generate"
    try:
        _post(url, {"model": tag, "keep_alive": 0}, timeout=30)
        return True
    except (urllib.error.URLError, TimeoutError):
        return False
