"""OpenAI-compatible chat completions (OpenAI, Azure OpenAI, vLLM and similar servers).

``POST {base_url}/chat/completions`` with ``Authorization: Bearer <key>``; body ``model``,
``messages`` (system message first), optional ``temperature`` and a token limit; answer
``choices[0].message.content`` and ``usage.prompt_tokens`` / ``usage.completion_tokens``.

Checked on 2026-10-27 against Microsoft's "Azure OpenAI REST reference v1" (Create chat
completion: ``{endpoint}/openai/v1/chat/completions``, ``max_completion_tokens`` preferred
and ``max_tokens`` deprecated, response example with ``choices`` and ``usage``) and Ollama's
OpenAI compatibility page (``/v1/chat/completions``, ``max_tokens``). OpenAI's own API
reference could not be fetched (HTTP 403 and 404 on every address tried), so the OpenAI side
is verified through those two sources only. Hosted OpenAI and Azure addresses get
``max_completion_tokens``; any other server gets ``max_tokens``.
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


def _uses_max_completion_tokens(base_url: str) -> bool:
    host = httpx.URL(base_url).host.lower()
    return host == "api.openai.com" or host.endswith(".openai.azure.com")


class OpenAICompatibleProvider:
    name = "openai_compatible"

    def __init__(
        self, config: ProviderConfig, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        if not config.base_url:
            raise AINotConfiguredError("No address is set for the OpenAI-compatible provider.")
        self._config = config
        self._base = config.base_url.rstrip("/")
        self._transport = transport

    async def generate_structured(self, request: GuardedRequest) -> Completion:
        messages = [{"role": "system", "content": request.system}]
        messages += [{"role": m.role, "content": m.content} for m in request.messages]
        limit = "max_completion_tokens" if _uses_max_completion_tokens(self._base) else "max_tokens"
        body: dict[str, object] = {
            "model": self._config.model,
            "messages": messages,
            limit: request.max_output_tokens,
        }
        if request.temperature is not None:
            body["temperature"] = request.temperature
        headers = {"content-type": "application/json"}
        if self._config.api_key:
            headers["authorization"] = f"Bearer {self._config.api_key}"
        async with client_for(self._transport) as client:
            response = await post_json(
                client,
                f"{self._base}/chat/completions",
                headers=headers,
                body=body,
                api_key=self._config.api_key,
            )
        data = json_body(response)
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ProviderError("The provider's answer had no choices.")
        message = choices[0].get("message")
        content = message.get("content") if isinstance(message, dict) else None
        usage = data.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        return Completion(
            text=content if isinstance(content, str) else "",
            input_tokens=int_or_zero(usage.get("prompt_tokens")),
            output_tokens=int_or_zero(usage.get("completion_tokens")),
            model=str(data.get("model") or self._config.model),
            request_id=response.headers.get("x-request-id"),
        )
