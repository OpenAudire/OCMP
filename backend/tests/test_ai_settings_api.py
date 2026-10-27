"""Tests for the admin AI settings API: permissions, rules, write-only keys, audit, test button."""

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.ai_settings import ai_transport
from app.core.config import Settings
from app.core.secrets import SecretBox, new_key
from app.models import AIProviderConfig, AIRun, AIRunCall, AISettings, AuditLog
from app.models.mapping import AIRunStatus, AIRunType
from tests.factories import InstitutionFactory
from tests.test_curriculum_edit_api import sign_in

API = "/api/v1/ai"
KEY = "sk-ant-test-not-a-real-key-0000"
OLLAMA = {"model": "llama-test", "base_url": "http://ollama:11434"}
ANTHROPIC_OK = {
    "content": [{"type": "text", "text": "ready"}],
    "usage": {"input_tokens": 20, "output_tokens": 2},
    "model": "claude-sonnet-5-5",
}


@pytest.fixture(autouse=True)
async def institution(db_session: AsyncSession, system_roles: None) -> None:
    db_session.add(InstitutionFactory.build())
    await db_session.flush()


@pytest.fixture
async def admin(api_client: AsyncClient, db_session: AsyncSession, test_settings: Settings) -> None:
    await sign_in(api_client, db_session, test_settings, "platform_admin")


@pytest.fixture
def provider_answers(api_app: Any) -> Callable[..., list[httpx.Request]]:
    """Make provider calls answer with a fixed response; returns the requests seen."""

    def install(status: int = 200, body: Any = ANTHROPIC_OK) -> list[httpx.Request]:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(status, json=body)

        api_app.dependency_overrides[ai_transport] = lambda: httpx.MockTransport(handler)
        return seen

    return install


async def patch(client: AsyncClient, body: dict[str, Any]) -> httpx.Response:
    return await client.patch(f"{API}/settings", json=body)


def provider(body: dict[str, Any], kind: str) -> dict[str, Any]:
    return next(p for p in body["providers"] if p["kind"] == kind)


async def use_anthropic(client: AsyncClient, **extra: Any) -> httpx.Response:
    return await patch(
        client,
        {
            "local_only": False,
            "active_provider": "anthropic",
            "acknowledge_outside_south_africa": True,
            "providers": {
                "anthropic": {
                    "model": "claude-sonnet-5-5",
                    "api_key": KEY,
                    "input_price_per_mtok": "1.00",
                    "output_price_per_mtok": "5.00",
                }
            },
            **extra,
        },
    )


class TestAccess:
    @pytest.mark.parametrize(
        ("method", "path"),
        [("GET", "/settings"), ("PATCH", "/settings"), ("POST", "/test-connection")],
    )
    async def test_requires_sign_in(self, api_client: AsyncClient, method: str, path: str) -> None:
        response = await api_client.request(method, f"{API}{path}", json={})
        assert response.status_code == 401

    @pytest.mark.parametrize(
        ("method", "path"),
        [("GET", "/settings"), ("PATCH", "/settings"), ("POST", "/test-connection")],
    )
    @pytest.mark.parametrize("role", [None, "student"])
    async def test_needs_settings_manage(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        method: str,
        path: str,
        role: str | None,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, role)

        response = await api_client.request(method, f"{API}{path}", json={})

        assert response.status_code == 403


@pytest.mark.usefixtures("admin")
class TestDefaults:
    async def test_ai_is_off_and_local_only_by_default(self, api_client: AsyncClient) -> None:
        response = await api_client.get(f"{API}/settings")

        assert response.status_code == 200
        body = response.json()
        assert body["active_provider"] == "null"
        assert body["local_only"] is True
        assert body["on_personal_data"] == "refuse"
        assert body["status"] == {"state": "off", "reasons": [], "budget_message": None}
        assert body["budget"] == {
            "monthly_cost_cap": "10.00",
            "monthly_token_cap": 2_000_000,
            "monthly_call_cap": 2000,
            "max_calls_per_run": 500,
            "max_output_tokens": 1024,
        }
        assert body["usage"]["calls"] == 0
        assert [p["kind"] for p in body["providers"]] == [
            "anthropic",
            "openai_compatible",
            "ollama",
        ]

    async def test_provider_metadata(self, api_client: AsyncClient) -> None:
        body = (await api_client.get(f"{API}/settings")).json()

        anthropic = provider(body, "anthropic")
        assert anthropic["outside_south_africa"] is True
        assert anthropic["data_location_fixed"] is True
        assert anthropic["key_mode"] == "required"
        assert "claude-sonnet-5-5" in anthropic["suggested_models"]
        assert anthropic["missing"] == ["model", "api_key"]
        ollama = provider(body, "ollama")
        assert ollama["is_local"] is True
        assert ollama["key_mode"] == "none"
        assert provider(body, "openai_compatible")["outside_south_africa"] is True


@pytest.mark.usefixtures("admin")
class TestChoosingAProvider:
    async def test_a_local_provider_can_be_chosen_in_local_only_mode(
        self, api_client: AsyncClient
    ) -> None:
        response = await patch(
            api_client, {"active_provider": "ollama", "providers": {"ollama": OLLAMA}}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["active_provider"] == "ollama"
        assert body["status"]["state"] == "ready"
        assert provider(body, "ollama")["base_url"] == "http://ollama:11434"

    async def test_an_incomplete_provider_cannot_be_chosen(self, api_client: AsyncClient) -> None:
        response = await patch(api_client, {"active_provider": "ollama"})

        assert response.status_code == 422
        assert "model" in response.json()["detail"]

    async def test_local_only_mode_refuses_a_provider_outside_the_network(
        self, api_client: AsyncClient
    ) -> None:
        response = await patch(
            api_client,
            {
                "active_provider": "anthropic",
                "acknowledge_outside_south_africa": True,
                "providers": {"anthropic": {"model": "claude-sonnet-5-5", "api_key": KEY}},
            },
        )

        assert response.status_code == 422
        assert "Local-only" in response.json()["detail"]
        assert KEY not in response.text

    async def test_outside_south_africa_needs_an_acknowledgement(
        self, api_client: AsyncClient
    ) -> None:
        response = await use_anthropic(api_client, acknowledge_outside_south_africa=False)

        assert response.status_code == 422
        assert "outside South Africa" in response.json()["detail"]
        assert (await api_client.get(f"{API}/settings")).json()["active_provider"] == "null"

    async def test_acknowledging_lets_it_be_chosen(self, api_client: AsyncClient) -> None:
        response = await use_anthropic(api_client)

        assert response.status_code == 200
        body = response.json()
        assert body["active_provider"] == "anthropic"
        assert body["acknowledgement"]["current"] is True
        assert body["acknowledgement"]["acknowledged_at"] is not None
        assert body["status"]["state"] == "ready"

    async def test_turning_local_only_on_again_needs_a_local_provider(
        self, api_client: AsyncClient
    ) -> None:
        await use_anthropic(api_client)

        response = await patch(api_client, {"local_only": True})

        assert response.status_code == 422

    async def test_switching_back_to_null_turns_ai_off(self, api_client: AsyncClient) -> None:
        await use_anthropic(api_client)

        body = (await patch(api_client, {"active_provider": "null", "local_only": True})).json()

        assert body["status"]["state"] == "off"

    async def test_an_acknowledgement_stops_covering_a_provider_that_changed(
        self, api_client: AsyncClient
    ) -> None:
        await patch(
            api_client,
            {
                "local_only": False,
                "active_provider": "openai_compatible",
                "acknowledge_outside_south_africa": True,
                "providers": {
                    "openai_compatible": {
                        "model": "m",
                        "base_url": "https://api.one.example/v1",
                        "api_key": KEY,
                    }
                },
            },
        )

        response = await patch(
            api_client,
            {"providers": {"openai_compatible": {"base_url": "https://api.two.example/v1"}}},
        )

        assert response.status_code == 422
        assert "Acknowledge" in response.json()["detail"]

    async def test_a_south_african_provider_needs_no_acknowledgement(
        self, api_client: AsyncClient
    ) -> None:
        response = await patch(
            api_client,
            {
                "local_only": False,
                "active_provider": "openai_compatible",
                "providers": {
                    "openai_compatible": {
                        "model": "m",
                        "base_url": "https://llm.campus.example/v1",
                        "data_location": "south_africa",
                        "input_price_per_mtok": "0",
                        "output_price_per_mtok": "0",
                    }
                },
            },
        )

        assert response.status_code == 200
        assert response.json()["status"]["state"] == "ready"

    async def test_anthropic_location_and_address_are_fixed(self, api_client: AsyncClient) -> None:
        for change in ({"data_location": "local"}, {"base_url": "https://other.example"}):
            response = await patch(api_client, {"providers": {"anthropic": change}})
            assert response.status_code == 422

    async def test_a_local_provider_must_be_on_a_private_address(
        self, api_client: AsyncClient
    ) -> None:
        response = await patch(
            api_client,
            {"providers": {"ollama": {"base_url": "https://gpu.example.org", "model": "m"}}},
        )

        assert response.status_code == 422
        assert "marked local" in response.json()["detail"]

    async def test_unknown_fields_are_refused(self, api_client: AsyncClient) -> None:
        response = await patch(api_client, {"surprise": True})
        assert response.status_code == 422


@pytest.mark.usefixtures("admin")
class TestKeysAreWriteOnly:
    async def test_a_key_is_never_returned(self, api_client: AsyncClient) -> None:
        patched = await use_anthropic(api_client)
        fetched = await api_client.get(f"{API}/settings")

        for response in (patched, fetched):
            assert KEY not in response.text
            entry = provider(response.json(), "anthropic")
            assert "api_key" not in entry["missing"]
            assert entry["key_status"] == "set"
            assert entry["key_set_at"] is not None
            assert not [
                k for k in entry if "key" in k and k not in ("key_mode", "key_status", "key_set_at")
            ]

    async def test_the_key_is_stored_encrypted(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await use_anthropic(api_client)

        stored = await db_session.scalar(select(AIProviderConfig.api_key_encrypted))

        assert stored is not None
        assert KEY not in stored
        assert stored.startswith("ocmp1:")

    async def test_the_key_is_not_in_the_audit_log(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await use_anthropic(api_client)
        await patch(api_client, {"providers": {"anthropic": {"api_key": KEY + "-second"}}})

        rows = (await db_session.scalars(select(AuditLog))).all()
        text = json.dumps(
            [[r.before, r.after, r.context, r.entity_type, r.action] for r in rows], default=str
        )

        assert KEY not in text
        updates = [
            r for r in rows if r.entity_type == "ai_provider_configs" and r.action == "update"
        ]
        assert updates, "the key change is audited"
        assert updates[-1].context["unrecorded_fields"] == ["api_key_encrypted"]
        assert updates[-1].context["operation"] == "ai.settings_update"
        assert updates[-1].actor_id is not None

    async def test_a_blank_key_is_refused(self, api_client: AsyncClient) -> None:
        response = await patch(api_client, {"providers": {"anthropic": {"api_key": "   "}}})
        assert response.status_code == 422

    async def test_ollama_takes_no_key(self, api_client: AsyncClient) -> None:
        response = await patch(api_client, {"providers": {"ollama": {"api_key": KEY}}})
        assert response.status_code == 422

    async def test_the_key_cannot_be_cleared_while_the_provider_is_in_use(
        self, api_client: AsyncClient
    ) -> None:
        await use_anthropic(api_client)

        response = await patch(api_client, {"providers": {"anthropic": {"clear_api_key": True}}})

        assert response.status_code == 422
        assert "api_key" in response.json()["detail"]

    async def test_a_key_can_be_cleared_once_unused(self, api_client: AsyncClient) -> None:
        await use_anthropic(api_client)
        await patch(api_client, {"active_provider": "null"})

        body = (
            await patch(api_client, {"providers": {"anthropic": {"clear_api_key": True}}})
        ).json()

        assert provider(body, "anthropic")["key_status"] == "not_set"

    async def test_a_key_that_cannot_be_decrypted_is_reported(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
    ) -> None:
        await use_anthropic(api_client)
        config = await db_session.scalar(select(AIProviderConfig))
        assert config is not None
        config.api_key_encrypted = SecretBox([new_key()]).encrypt(KEY)
        await db_session.flush()

        body = (await api_client.get(f"{API}/settings")).json()

        assert provider(body, "anthropic")["key_status"] == "unreadable"
        assert "api_key" in provider(body, "anthropic")["missing"]
        assert body["status"]["state"] == "blocked"
        assert body["status"]["reasons"] == ["not_configured"]


@pytest.mark.usefixtures("admin")
class TestBudgets:
    async def test_limits_can_be_changed_and_removed(self, api_client: AsyncClient) -> None:
        body = (
            await patch(
                api_client,
                {
                    "monthly_cost_cap": "25.50",
                    "monthly_token_cap": None,
                    "monthly_call_cap": 10,
                    "max_calls_per_run": 20,
                    "max_output_tokens": 512,
                },
            )
        ).json()

        assert body["budget"] == {
            "monthly_cost_cap": "25.50",
            "monthly_token_cap": None,
            "monthly_call_cap": 10,
            "max_calls_per_run": 20,
            "max_output_tokens": 512,
        }

    @pytest.mark.parametrize(
        "change",
        [
            {"monthly_cost_cap": -1},
            {"monthly_call_cap": -5},
            {"max_calls_per_run": 0},
            {"max_output_tokens": 0},
        ],
    )
    async def test_invalid_limits_are_refused(
        self, api_client: AsyncClient, change: dict[str, Any]
    ) -> None:
        assert (await patch(api_client, change)).status_code == 422

    async def test_a_reached_limit_shows_as_a_blocked_state(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await patch(api_client, {"active_provider": "ollama", "providers": {"ollama": OLLAMA}})
        await patch(api_client, {"monthly_call_cap": 1})
        run = AIRun(
            type=AIRunType.MAPPING,
            status=AIRunStatus.SUCCEEDED,
            provider="ollama",
            model="m",
            prompt_version="t:1",
        )
        db_session.add(run)
        await db_session.flush()
        db_session.add(AIRunCall(run_id=run.id, request={}, input_tokens=5, output_tokens=5))
        await db_session.flush()

        body = (await api_client.get(f"{API}/settings")).json()

        assert body["usage"]["calls"] == 1
        assert body["usage"]["tokens"] == 10
        assert body["status"]["state"] == "blocked"
        assert body["status"]["reasons"] == ["budget_exceeded"]
        assert "monthly limit of 1 AI calls" in body["status"]["budget_message"]


@pytest.mark.usefixtures("admin")
class TestTestConnection:
    async def test_succeeds_and_records_a_run(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        provider_answers: Callable[..., list[httpx.Request]],
    ) -> None:
        seen = provider_answers()
        await use_anthropic(api_client)

        response = await api_client.post(f"{API}/test-connection")

        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert body["code"] == "ok"
        assert body["provider"] == "anthropic"
        assert (body["input_tokens"], body["output_tokens"]) == (20, 2)
        assert KEY not in response.text
        # One request, the fixed prompt only, the key in the header only.
        assert len(seen) == 1
        sent = json.loads(seen[0].content)
        assert sent["messages"] == [
            {"role": "user", "content": "Reply with the single word: ready"}
        ]
        assert seen[0].headers["x-api-key"] == KEY
        run = await db_session.scalar(select(AIRun))
        assert run is not None
        assert run.type is AIRunType.CONNECTION_TEST
        assert run.status is AIRunStatus.SUCCEEDED
        assert (run.input_tokens, run.output_tokens) == (20, 2)

    async def test_nothing_is_sent_unless_the_button_is_pressed(
        self, api_client: AsyncClient, provider_answers: Callable[..., list[httpx.Request]]
    ) -> None:
        seen = provider_answers()

        await use_anthropic(api_client)
        await api_client.get(f"{API}/settings")

        assert seen == []

    async def test_off_means_nothing_is_sent(
        self, api_client: AsyncClient, provider_answers: Callable[..., list[httpx.Request]]
    ) -> None:
        seen = provider_answers()

        body = (await api_client.post(f"{API}/test-connection")).json()

        assert body["ok"] is False
        assert body["code"] == "ai_disabled"
        assert body["provider"] == "null"
        assert seen == []

    async def test_a_provider_error_is_reported_without_the_key(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        provider_answers: Callable[..., list[httpx.Request]],
    ) -> None:
        provider_answers(
            401,
            {"type": "error", "error": {"type": "authentication_error", "message": f"bad {KEY}"}},
        )
        await use_anthropic(api_client)

        response = await api_client.post(f"{API}/test-connection")

        body = response.json()
        assert body["ok"] is False
        assert body["code"] == "provider_error"
        assert "401" in body["message"]
        assert KEY not in response.text
        run = await db_session.scalar(select(AIRun))
        assert run is not None
        assert run.status is AIRunStatus.FAILED
        assert KEY not in (run.error_message or "")
        call = await db_session.scalar(select(AIRunCall))
        assert call is not None
        assert KEY not in (call.error_message or "")

    async def test_a_reached_budget_refuses_before_sending(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        provider_answers: Callable[..., list[httpx.Request]],
    ) -> None:
        seen = provider_answers()
        await use_anthropic(api_client, monthly_call_cap=0)

        body = (await api_client.post(f"{API}/test-connection")).json()

        assert body["ok"] is False
        assert body["code"] == "budget_exceeded"
        assert "monthly limit" in body["message"]
        assert seen == []
        run = await db_session.scalar(select(AIRun))
        assert run is not None
        assert run.status is AIRunStatus.BUDGET_EXCEEDED

    async def test_is_rate_limited(
        self, api_client: AsyncClient, provider_answers: Callable[..., list[httpx.Request]]
    ) -> None:
        provider_answers()
        statuses = [(await api_client.post(f"{API}/test-connection")).status_code for _ in range(7)]

        assert statuses[:5] == [200] * 5
        assert statuses[5:] == [429, 429]

    async def test_the_test_is_audited(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await api_client.post(f"{API}/test-connection")

        events = (
            await db_session.scalars(select(AuditLog).where(AuditLog.action == "connection_test"))
        ).all()

        assert len(events) == 1
        assert events[0].context["operation"] == "ai.connection_test"
        assert events[0].actor_id is not None


@pytest.mark.usefixtures("admin")
class TestTurningAiOff:
    async def test_withdraws_the_acknowledgement(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await use_anthropic(api_client)

        body = (await patch(api_client, {"active_provider": "null"})).json()

        assert body["acknowledgement"] == {"acknowledged_at": None, "current": False}
        row = await db_session.scalar(select(AISettings))
        assert row is not None
        assert (row.ack_provider_key, row.ack_by_id, row.ack_at) == (None, None, None)
        # Choosing it again needs a fresh acknowledgement.
        again = await patch(
            api_client,
            {"local_only": False, "active_provider": "anthropic"},
        )
        assert again.status_code == 422
        assert "Acknowledge" in again.json()["detail"]
