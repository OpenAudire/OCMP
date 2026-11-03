"""Anthropic Claude through the Messages API.

Checked against https://platform.claude.com/docs/en/api/messages, .../get-started,
.../api/errors and .../models/overview on 2026-10-27: ``POST {base}/v1/messages`` with
headers ``x-api-key``, ``anthropic-version: 2023-06-01`` and ``content-type``; body
``model``, ``max_tokens``, ``system`` (top-level), ``messages`` and optional
``temperature``; answer ``content`` blocks of type ``text`` and ``usage.input_tokens`` /
``usage.output_tokens``; errors ``{"type": "error", "error": {"type", "message"}}``.
``temperature`` is sent only when the admin set one (current models were not checked for
accepting it). Structured output is requested in the prompt, not with an API feature.
"""

import httpx

from app.ai.errors import AINotConfiguredError, ProviderError
from app.ai.privacy import GuardedRequest
from app.ai.providers.base import (
    Completion,
    ProviderConfig,
    client_for,
    int_or_zero,
    json_body,
    post_json,
)

BASE_URL = "https://api.anthropic.com"
API_VERSION = "2023-06-01"
# Model ids from the models overview page read on 2026-10-27 (a suggestion, not a limit).
SUGGESTED_MODELS = ("claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-1")


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self, config: ProviderConfig, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        if not config.api_key:
            raise AINotConfiguredError("No Anthropic API key is stored.")
        self._config = config
        self._transport = transport

    async def generate_structured(self, request: GuardedRequest) -> Completion:
        body: dict[str, object] = {
            "model": self._config.model,
            "max_tokens": request.max_output_tokens,
            "system": request.system,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
        }
        if request.temperature is not None:
            body["temperature"] = request.temperature
        headers = {
            "x-api-key": self._config.api_key or "",
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        }
        base = (self._config.base_url or BASE_URL).rstrip("/")
        async with client_for(self._transport) as client:
            response = await post_json(
                client,
                f"{base}/v1/messages",
                headers=headers,
                body=body,
                api_key=self._config.api_key,
            )
        data = json_body(response)
        blocks = data.get("content")
        if not isinstance(blocks, list):
            raise ProviderError("The provider's answer had no content.")
        text = "".join(
            str(b.get("text", ""))
            for b in blocks
            if isinstance(b, dict) and b.get("type") == "text"
        )
        usage = data.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        return Completion(
            text=text,
            input_tokens=int_or_zero(usage.get("input_tokens")),
            output_tokens=int_or_zero(usage.get("output_tokens")),
            model=str(data.get("model") or self._config.model),
            request_id=response.headers.get("request-id"),
            truncated=data.get("stop_reason") == "max_tokens",
        )
