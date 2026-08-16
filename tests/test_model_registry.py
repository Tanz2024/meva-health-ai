"""Tests for MEVA's local model registry and configuration.

Fully offline — no Ollama calls here (that's meva.models.discovery, tested
separately in test_model_comparison.py with mocks).
"""

import pytest
from pydantic import ValidationError

from meva.models import MODEL_REGISTRY, UnknownModelError, get_model_config, list_registered_models
from meva.models.config import ModelConfig


def test_model_registry_contains_both_models():
    assert set(list_registered_models()) == {"qwen3:4b", "llama3.2:3b"}


def test_model_lookup_returns_config():
    config = get_model_config("qwen3:4b")
    assert config.ollama_tag == "qwen3:4b"
    assert config.provider == "ollama-local"


def test_unknown_model_lookup_raises():
    with pytest.raises(UnknownModelError, match="not registered"):
        get_model_config("gpt-4")


def test_model_lookup_returns_a_copy_not_the_registry_object():
    config = get_model_config("qwen3:4b")
    config.temperature = 99
    assert MODEL_REGISTRY["qwen3:4b"].temperature == 0  # untouched


def test_cloud_tag_rejected():
    with pytest.raises(ValidationError, match="Cloud model tags are not allowed"):
        ModelConfig(name="bad", ollama_tag="qwen3:cloud")


def test_no_registered_model_uses_a_cloud_tag():
    for name, config in MODEL_REGISTRY.items():
        assert ":cloud" not in config.ollama_tag, name


def test_metadata_defaults_to_none_before_discovery():
    config = get_model_config("qwen3:4b")
    assert config.digest is None
    assert config.parameter_size is None
    assert config.quantization is None
    assert config.capabilities is None
