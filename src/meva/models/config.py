"""ModelConfig: everything MEVA needs to know to run one local Ollama model fairly.

This does not duplicate the agent — meva.ai.agent already accepts a
`model` name and generation settings. ModelConfig just bundles those
settings, plus metadata that's queried live from Ollama (never
hardcoded/guessed), so every model in a comparison is described the
same way.
"""

from pydantic import BaseModel, field_validator


class ModelConfig(BaseModel):
    """Configuration + (once queried) metadata for one local Ollama model."""

    name: str
    ollama_tag: str
    provider: str = "ollama-local"

    # Generation settings — see docs/reproducibility.md. Every registered model
    # uses the same values unless a model genuinely can't support one (see
    # meva.models.discovery, which records that as *_supported=False rather
    # than silently omitting or faking the setting).
    tool_think: bool = True
    structured_think: bool = False
    temperature: float = 0
    seed: int = 42
    keep_alive: str = "5m"

    # Metadata — always populated from a live Ollama query (meva.models.discovery),
    # never hardcoded. None until queried.
    parameter_size: str | None = None
    quantization: str | None = None
    digest: str | None = None
    capabilities: list[str] | None = None
    license_name: str | None = None

    @field_validator("ollama_tag")
    @classmethod
    def _reject_cloud_tags(cls, value: str) -> str:
        if ":cloud" in value:
            raise ValueError(f"Cloud model tags are not allowed in MEVA: '{value}'")
        return value
