"""AI provider factory."""

from __future__ import annotations

from gemsieve.ai.base import AIProvider
from gemsieve.ai.ollama import OllamaProvider
from gemsieve.ai.anthropic_provider import AnthropicProvider


def get_provider(model_spec: str, config: dict | None = None) -> tuple[AIProvider, str]:
    """Parse 'provider:model_name' and return (provider_instance, model_name).

    If no colon is present, assumes ollama as the provider.
    """
    if ":" in model_spec:
        provider_name, model_name = model_spec.split(":", 1)
    else:
        provider_name = "ollama"
        model_name = model_spec

    config = config or {}

    if provider_name == "ollama":
        base_url = config.get("ollama_base_url", "http://localhost:11434")
        api_key = config.get("ollama_api_key", "")
        return OllamaProvider(base_url=base_url, api_key=api_key), model_name
    elif provider_name == "anthropic":
        return AnthropicProvider(), model_name
    else:
        raise ValueError(f"Unknown AI provider: {provider_name!r}. Use 'ollama' or 'anthropic'.")
