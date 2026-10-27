"""Tests for the provider adapters, using httpx.MockTransport (no network is ever used)."""

import json
from typing import Any, ClassVar

import httpx
import pytest

from app.ai import prompts
from app.ai.errors import AIDisabledError, AINotConfiguredError, ProviderError
from app.ai.locality import is_local_host, normalise_base_url
from app.ai.privacy import GuardedRequest, PromptTemplate, prepare
from app.ai.providers import ProviderConfig, build_provider
from app.models.ai_settings import AIProviderKind, DataLocation, PersonalDataAction
from app.services.authorization import InvalidRequestError

KEY = "sk-test-not-a-real-key-123456"


def guarded(
    template: PromptTemplate = prompts.CONNECTION_TEST,
    temperature: float | None = None,
    **fields: str,
) -> GuardedRequest:
    return prepare(
        template,
        fields,
        known_names=None,
        action=PersonalDataAction.REFUSE,
        max_output_tokens=50,
        temperature=temperature,
    )


class Recorder:
    """A mock transport that records the request and answers with a fixed response."""

    def __init__(self, status: int = 200, body: Any = None, headers: dict[str, str] | None = None):
        self.status = status
        self.body = body
        self.headers = headers or {}
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status, json=self.body, headers=self.headers)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)

    @property
    def sent(self) -> dict[str, Any]:
        return json.loads(self.requests[-1].content)


class TestAnthropic:
    OK: ClassVar[dict[str, Any]] = {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-5-5",
        "content": [
            {"type": "thinking", "thinking": "hmm"},
            {"type": "text", "text": "rea"},
            {"type": "text", "text": "dy"},
        ],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 21, "output_tokens": 5},
    }

    async def test_request_shape_follows_the_messages_api(self) -> None:
        recorder = Recorder(body=self.OK, headers={"request-id": "req_1"})
        provider = build_provider(
            AIProviderKind.ANTHROPIC,
            ProviderConfig(model="claude-sonnet-5-5", api_key=KEY),
            recorder.transport,
        )

        result = await provider.generate_structured(guarded())

        request = recorder.requests[0]
        assert str(request.url) == "https://api.anthropic.com/v1/messages"
        assert request.headers["x-api-key"] == KEY
        assert request.headers["anthropic-version"] == "2023-06-01"
        assert recorder.sent == {
            "model": "claude-sonnet-5-5",
            "max_tokens": 50,
            "system": prompts.CONNECTION_TEST.system,
            "messages": [{"role": "user", "content": prompts.CONNECTION_TEST.user}],
        }
        assert result.text == "ready"
        assert (result.input_tokens, result.output_tokens) == (21, 5)
        assert result.request_id == "req_1"

    async def test_temperature_is_sent_only_when_set(self) -> None:
        recorder = Recorder(body=self.OK)
        provider = build_provider(
            AIProviderKind.ANTHROPIC,
            ProviderConfig(model="m", api_key=KEY),
            recorder.transport,
        )

        await provider.generate_structured(guarded(temperature=0.2))

        assert recorder.sent["temperature"] == 0.2

    async def test_error_status_becomes_a_provider_error_without_the_key(self) -> None:
        recorder = Recorder(
            status=401,
            body={
                "type": "error",
                "error": {"type": "authentication_error", "message": f"bad key {KEY}"},
            },
        )
        provider = build_provider(
            AIProviderKind.ANTHROPIC, ProviderConfig(model="m", api_key=KEY), recorder.transport
        )

        with pytest.raises(ProviderError) as error:
            await provider.generate_structured(guarded())

        assert error.value.status_code == 401
        assert "401" in str(error.value)
        assert KEY not in str(error.value)

    async def test_needs_a_key(self) -> None:
        with pytest.raises(AINotConfiguredError):
            build_provider(AIProviderKind.ANTHROPIC, ProviderConfig(model="m"))

    async def test_a_redirect_is_an_error_not_followed(self) -> None:
        def redirect(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(302, headers={"location": "https://evil.example/steal"})

        provider = build_provider(
            AIProviderKind.ANTHROPIC,
            ProviderConfig(model="m", api_key=KEY),
            httpx.MockTransport(redirect),
        )

        with pytest.raises(ProviderError, match="302"):
            await provider.generate_structured(guarded())

    async def test_unreachable_provider(self) -> None:
        def refuse(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route", request=request)

        provider = build_provider(
            AIProviderKind.ANTHROPIC,
            ProviderConfig(model="m", api_key=KEY),
            httpx.MockTransport(refuse),
        )

        with pytest.raises(ProviderError, match="could not be reached"):
            await provider.generate_structured(guarded())

    async def test_answer_without_content_is_an_error(self) -> None:
        recorder = Recorder(body={"usage": {}})
        provider = build_provider(
            AIProviderKind.ANTHROPIC, ProviderConfig(model="m", api_key=KEY), recorder.transport
        )

        with pytest.raises(ProviderError, match="no content"):
            await provider.generate_structured(guarded())


class TestOpenAICompatible:
    OK: ClassVar[dict[str, Any]] = {
        "id": "chatcmpl-1",
        "model": "gpt-test",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": "ready"},
            }
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15},
    }

    async def test_request_shape_for_hosted_openai(self) -> None:
        recorder = Recorder(body=self.OK)
        provider = build_provider(
            AIProviderKind.OPENAI_COMPATIBLE,
            ProviderConfig(model="gpt-test", base_url="https://api.openai.com/v1", api_key=KEY),
            recorder.transport,
        )

        result = await provider.generate_structured(guarded())

        request = recorder.requests[0]
        assert str(request.url) == "https://api.openai.com/v1/chat/completions"
        assert request.headers["authorization"] == f"Bearer {KEY}"
        assert recorder.sent["model"] == "gpt-test"
        assert recorder.sent["max_completion_tokens"] == 50
        assert "max_tokens" not in recorder.sent
        assert [m["role"] for m in recorder.sent["messages"]] == ["system", "user"]
        assert result.text == "ready"
        assert (result.input_tokens, result.output_tokens) == (12, 3)

    async def test_other_servers_get_max_tokens_and_need_no_key(self) -> None:
        recorder = Recorder(body=self.OK)
        provider = build_provider(
            AIProviderKind.OPENAI_COMPATIBLE,
            ProviderConfig(model="local", base_url="http://vllm:8000/v1/"),
            recorder.transport,
        )

        await provider.generate_structured(guarded())

        assert str(recorder.requests[0].url) == "http://vllm:8000/v1/chat/completions"
        assert "authorization" not in recorder.requests[0].headers
        assert recorder.sent["max_tokens"] == 50
        assert "max_completion_tokens" not in recorder.sent

    async def test_null_content_gives_empty_text(self) -> None:
        body = {"choices": [{"message": {"content": None}}], "usage": {}}
        provider = build_provider(
            AIProviderKind.OPENAI_COMPATIBLE,
            ProviderConfig(model="m", base_url="http://x/v1"),
            Recorder(body=body).transport,
        )

        result = await provider.generate_structured(guarded())

        assert result.text == ""
        assert result.input_tokens == 0

    async def test_error_message_is_trimmed_and_the_key_removed(self) -> None:
        recorder = Recorder(
            status=429, body={"error": {"message": f"slow down {KEY} " + "x" * 600}}
        )
        provider = build_provider(
            AIProviderKind.OPENAI_COMPATIBLE,
            ProviderConfig(model="m", base_url="https://api.openai.com/v1", api_key=KEY),
            recorder.transport,
        )

        with pytest.raises(ProviderError) as error:
            await provider.generate_structured(guarded())

        assert KEY not in str(error.value)
        assert len(str(error.value)) < 400

    async def test_no_choices_is_an_error(self) -> None:
        provider = build_provider(
            AIProviderKind.OPENAI_COMPATIBLE,
            ProviderConfig(model="m", base_url="http://x/v1"),
            Recorder(body={"choices": []}).transport,
        )

        with pytest.raises(ProviderError, match="no choices"):
            await provider.generate_structured(guarded())


class TestOllama:
    OK: ClassVar[dict[str, Any]] = {
        "model": "llama-test",
        "message": {"role": "assistant", "content": "ready"},
        "done": True,
        "prompt_eval_count": 26,
        "eval_count": 4,
    }

    async def test_request_shape_follows_the_chat_api(self) -> None:
        recorder = Recorder(body=self.OK)
        provider = build_provider(
            AIProviderKind.OLLAMA,
            ProviderConfig(model="llama-test", base_url="http://ollama:11434/"),
            recorder.transport,
        )

        result = await provider.generate_structured(guarded(temperature=0.0))

        assert str(recorder.requests[0].url) == "http://ollama:11434/api/chat"
        assert recorder.sent["model"] == "llama-test"
        assert recorder.sent["stream"] is False
        assert recorder.sent["options"] == {"temperature": 0.0}
        assert "format" not in recorder.sent
        assert result.text == "ready"
        assert (result.input_tokens, result.output_tokens) == (26, 4)

    async def test_a_json_schema_goes_in_format(self) -> None:
        template = PromptTemplate(
            name="s", version="1", system="s", user="u", json_schema={"type": "object"}
        )
        recorder = Recorder(body=self.OK)
        provider = build_provider(
            AIProviderKind.OLLAMA,
            ProviderConfig(model="m", base_url="http://ollama:11434"),
            recorder.transport,
        )

        await provider.generate_structured(guarded(template))

        assert recorder.sent["format"] == {"type": "object"}

    async def test_needs_an_address(self) -> None:
        with pytest.raises(AINotConfiguredError):
            build_provider(AIProviderKind.OLLAMA, ProviderConfig(model="m"))

    async def test_model_not_found(self) -> None:
        provider = build_provider(
            AIProviderKind.OLLAMA,
            ProviderConfig(model="m", base_url="http://ollama:11434"),
            Recorder(status=404, body={"error": "model 'm' not found"}).transport,
        )

        with pytest.raises(ProviderError, match="404"):
            await provider.generate_structured(guarded())


async def test_the_null_provider_refuses_and_has_no_network_code() -> None:
    provider = build_provider(AIProviderKind.NULL, None)

    with pytest.raises(AIDisabledError):
        await provider.generate_structured(guarded())


class TestLocality:
    @pytest.mark.parametrize(
        "host",
        [
            "localhost",
            "127.0.0.1",
            "[::1]",
            "10.1.2.3",
            "192.168.0.5",
            "ollama",
            "gpu.lan",
            "x.internal",
        ],
    )
    def test_local_hosts(self, host: str) -> None:
        assert is_local_host(host) is True

    @pytest.mark.parametrize("host", ["api.openai.com", "8.8.8.8", "ollama.example.org", ""])
    def test_public_hosts(self, host: str) -> None:
        assert is_local_host(host) is False

    def test_a_local_provider_must_have_a_local_address(self) -> None:
        with pytest.raises(InvalidRequestError, match="marked local"):
            normalise_base_url("https://api.example.org/v1", DataLocation.LOCAL)

    def test_plain_http_only_on_private_networks(self) -> None:
        assert (
            normalise_base_url("http://ollama:11434/", DataLocation.LOCAL) == "http://ollama:11434"
        )
        with pytest.raises(InvalidRequestError, match="https"):
            normalise_base_url("http://api.example.org/v1", DataLocation.OUTSIDE_SOUTH_AFRICA)

    @pytest.mark.parametrize(
        "value",
        [
            "ftp://x/y",
            "not a url",
            "https://user:pw@api.example.org",
            "https://x.org/v1?key=1",
            "https:///v1",
        ],
    )
    def test_bad_addresses(self, value: str) -> None:
        with pytest.raises(InvalidRequestError):
            normalise_base_url(value, DataLocation.OUTSIDE_SOUTH_AFRICA)
