"""Ollama (a language model on the institution's own server).

Checked against https://github.com/ollama/ollama/blob/main/docs/api.md on 2026-10-27:
``POST {base}/api/chat`` with ``model``, ``messages``, ``stream: false``, optional
``format`` (``json`` or a JSON schema) and ``options`` (``temperature``); answer
``message.content``, ``prompt_eval_count`` and ``eval_count``. The page gives no error body
shape, only status codes, so any error status is reported by its number. ``num_predict`` is
not documented for chat there, so the output limit is not sent: the answer length is the
model's own.
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


class OllamaProvider:
    name = "ollama"

    def __init__(
        self, config: ProviderConfig, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        if not config.base_url:
            raise AINotConfiguredError("No Ollama address is set.")
        self._config = config
        self._base = config.base_url.rstrip("/")
        self._transport = transport

    async def generate_structured(self, request: GuardedRequest) -> Completion:
        messages = [{"role": "system", "content": request.system}]
        messages += [{"role": m.role, "content": m.content} for m in request.messages]
        body: dict[str, object] = {
            "model": self._config.model,
            "messages": messages,
            "stream": False,
        }
        if request.json_schema is not None:
            body["format"] = request.json_schema
        if request.temperature is not None:
            body["options"] = {"temperature": request.temperature}
        async with client_for(self._transport) as client:
            response = await post_json(
                client,
                f"{self._base}/api/chat",
                headers={"content-type": "application/json"},
                body=body,
                api_key=None,
            )
        data = json_body(response)
        message = data.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            raise ProviderError("The provider's answer had no message.")
        return Completion(
            text=content,
            input_tokens=int_or_zero(data.get("prompt_eval_count")),
            output_tokens=int_or_zero(data.get("eval_count")),
            model=str(data.get("model") or self._config.model),
        )
