"""MEVA's registered local models — the fixed, known set of models MEVA can benchmark.

Only local Ollama models are ever registered here. Adding a model means
adding one ModelConfig entry; nothing else in MEVA needs to change (see
docs/model-comparison.md).
"""

from meva.models.config import ModelConfig

MODEL_REGISTRY: dict[str, ModelConfig] = {
    "qwen3:4b": ModelConfig(name="qwen3:4b", ollama_tag="qwen3:4b"),
    "llama3.2:3b": ModelConfig(name="llama3.2:3b", ollama_tag="llama3.2:3b"),
}


class UnknownModelError(Exception):
    """Raised when a requested model name isn't registered."""


def get_model_config(name: str) -> ModelConfig:
    """Look up a registered model's base configuration (metadata not yet queried)."""
    if name not in MODEL_REGISTRY:
        raise UnknownModelError(
            f"Model '{name}' is not registered in MEVA. Registered models: {list_registered_models()}"
        )
    return MODEL_REGISTRY[name].model_copy()


def list_registered_models() -> list[str]:
    return list(MODEL_REGISTRY)
