"""MEVA's local-model registry and live-metadata discovery.

Everything here describes *which* Ollama models MEVA can run and *what
Ollama itself reports about them* — no model comparison logic lives
here. See src/meva/benchmark/comparison.py for that.
"""

from meva.models.config import ModelConfig
from meva.models.discovery import ModelNotInstalledError, describe_model, is_model_installed, think_supported
from meva.models.registry import MODEL_REGISTRY, UnknownModelError, get_model_config, list_registered_models

__all__ = [
    "ModelConfig",
    "MODEL_REGISTRY",
    "UnknownModelError",
    "get_model_config",
    "list_registered_models",
    "ModelNotInstalledError",
    "describe_model",
    "is_model_installed",
    "think_supported",
]
