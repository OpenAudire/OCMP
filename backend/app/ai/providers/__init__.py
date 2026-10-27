"""Provider adapters and the factory that picks one."""

import httpx

from app.ai.providers.anthropic import AnthropicProvider
from app.ai.providers.base import Completion, LLMProvider, ProviderConfig
from app.ai.providers.null import NullProvider
from app.ai.providers.ollama import OllamaProvider
from app.ai.providers.openai_compatible import OpenAICompatibleProvider
from app.models.ai_settings import AIProviderKind


def build_provider(
    kind: AIProviderKind,
    config: ProviderConfig | None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> LLMProvider:
    """The adapter for a provider kind. ``config`` is not needed for the Null provider."""
    if kind is AIProviderKind.NULL or config is None:
        return NullProvider()
    if kind is AIProviderKind.ANTHROPIC:
        return AnthropicProvider(config, transport)
    if kind is AIProviderKind.OPENAI_COMPATIBLE:
        return OpenAICompatibleProvider(config, transport)
    return OllamaProvider(config, transport)


__all__ = [
    "Completion",
    "LLMProvider",
    "NullProvider",
    "ProviderConfig",
    "build_provider",
]
