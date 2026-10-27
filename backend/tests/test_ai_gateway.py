"""Tests for the AI gateway: every outbound call, its checks, budgets, records and logs."""

import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from structlog.testing import capture_logs

from app.ai import prompts
from app.ai.errors import (
    AIAcknowledgementMissingError,
    AIBudgetExceededError,
    AIDisabledError,
    AILocalOnlyError,
    AINotConfiguredError,
    PersonalDataRefusedError,
    PrivacyViolationError,
    ProviderError,
)
from app.ai.privacy import PromptTemplate
from app.core.config import Settings
from app.core.secrets import SecretBox, new_key
from app.models import AIProviderConfig, AIRun, AIRunCall, AISettings, Institution, User
from app.models.ai_settings import AIProviderKind, DataLocation, PersonalDataAction
from app.models.mapping import AIRunStatus, AIRunType
from app.schemas.ai import AIUpdate
from app.services import ai_gateway, ai_settings
from tests.factories import InstitutionFactory, UserFactory

KEY = "sk-ant-test-not-a-real-key-0000"
TEMPLATE = PromptTemplate(
    name="compare",
    version="3",
    system="Compare an objective with a framework item.",
    user="Objective: {{objective_text}}",
)
ANSWER = {
    "content": [{"type": "text", "text": "match"}],
    "usage": {"input_tokens": 1000, "output_tokens": 500},
    "model": "claude-sonnet-5-5",
}


class Provider:
    """A mock provider that records requests and answers."""

    def __init__(self, status: int = 200, body: Any = ANSWER) -> None:
        self.status, self.body = status, body
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status, json=self.body)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)


@pytest.fixture
async def institution(db_session: AsyncSession) -> Institution:
    value = InstitutionFactory.build()
    db_session.add(value)
    await db_session.flush()
    return value


@pytest.fixture
async def admin(db_session: AsyncSession) -> User:
    user = UserFactory.build(display_name="Pat Admin")
    db_session.add(user)
    await db_session.flush()
    return user


async def configure(
    db: AsyncSession,
    institution: Institution,
    admin: User,
    settings: Settings,
    **change: Any,
) -> None:
    """Choose Anthropic, outside South Africa, acknowledged, priced."""
    values: dict[str, Any] = {
        "local_only": False,
        "active_provider": "anthropic",
        "acknowledge_outside_south_africa": True,
        "providers": {
            "anthropic": {
                "model": "claude-sonnet-5-5",
                "api_key": KEY,
                "input_price_per_mtok": "2",
                "output_price_per_mtok": "10",
            }
        },
        **change,
    }
    await ai_settings.update_ai_settings(
        db,
        institution,
        actor_id=admin.id,
        box=SecretBox.from_settings(settings),
        change=AIUpdate.model_validate(values),
    )


async def run_complete(
    db: AsyncSession, settings: Settings, provider: Provider, text: str = "Explain blood flow."
) -> ai_gateway.GatewayResult:
    return await ai_gateway.complete(
        db,
        settings,
        template=TEMPLATE,
        fields={"objective_text": text},
        run_type=AIRunType.MAPPING,
        actor_id=None,
        transport=provider.transport,
    )


class TestRefusalsBeforeAnythingIsSent:
    async def test_off_by_default(
        self, db_session: AsyncSession, test_settings: Settings, institution: Institution
    ) -> None:
        provider = Provider()

        with pytest.raises(AIDisabledError):
            await run_complete(db_session, test_settings, provider)

        assert provider.requests == []
        assert await db_session.scalar(select(AIRun.id)) is None

    async def test_local_only_blocks_a_cloud_provider(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        institution: Institution,
        admin: User,
    ) -> None:
        await configure(db_session, institution, admin, test_settings)
        row = await db_session.scalar(select(AISettings))
        assert row is not None
        row.local_only = True  # turned on after the provider was chosen
        provider = Provider()

        with pytest.raises(AILocalOnlyError):
            await run_complete(db_session, test_settings, provider)

        assert provider.requests == []

    async def test_a_changed_address_loses_the_acknowledgement(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        institution: Institution,
        admin: User,
    ) -> None:
        await configure(
            db_session,
            institution,
            admin,
            test_settings,
            active_provider="openai_compatible",
            providers={
                "openai_compatible": {
                    "model": "m",
                    "base_url": "https://api.one.example/v1",
                    "input_price_per_mtok": "1",
                    "output_price_per_mtok": "1",
                }
            },
        )
        config = await db_session.scalar(
            select(AIProviderConfig).where(
                AIProviderConfig.provider == AIProviderKind.OPENAI_COMPATIBLE
            )
        )
        assert config is not None
        config.base_url = "https://api.two.example/v1"
        provider = Provider()

        with pytest.raises(AIAcknowledgementMissingError):
            await run_complete(db_session, test_settings, provider)

        assert provider.requests == []

    async def test_an_unreadable_key_is_a_clear_refusal(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        institution: Institution,
        admin: User,
    ) -> None:
        await configure(db_session, institution, admin, test_settings)
        config = await db_session.scalar(select(AIProviderConfig))
        assert config is not None
        config.api_key_encrypted = SecretBox([new_key()]).encrypt(KEY)

        with pytest.raises(AINotConfiguredError):
            await run_complete(db_session, test_settings, Provider())


class TestSuccessfulCall:
    async def test_records_the_run_and_the_call(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        institution: Institution,
        admin: User,
    ) -> None:
        await configure(db_session, institution, admin, test_settings)
        provider = Provider()

        result = await run_complete(db_session, test_settings, provider)

        assert result.text == "match"
        assert (result.input_tokens, result.output_tokens) == (1000, 500)
        # 1000 tokens at USD 2 per million plus 500 at USD 10 per million.
        assert result.cost == Decimal("0.007")
        run = await db_session.scalar(select(AIRun))
        call = await db_session.scalar(select(AIRunCall))
        assert run is not None
        assert call is not None
        assert run.status is AIRunStatus.SUCCEEDED
        assert run.type is AIRunType.MAPPING
        assert (run.provider, run.model, run.prompt_version) == (
            "anthropic",
            "claude-sonnet-5-5",
            "compare:3",
        )
        assert run.estimated_cost == Decimal("0.007")
        assert run.finished_at is not None
        assert call.run_id == run.id
        assert call.response == "match"
        assert call.request["messages"][0]["content"] == "Objective: Explain blood flow."
        # The stored request is what the provider received.
        sent = json.loads(provider.requests[0].content)
        assert sent["messages"][0]["content"] == call.request["messages"][0]["content"]
        assert sent["system"] == call.request["system"]

    async def test_logs_hold_ids_and_counts_never_content_or_keys(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        institution: Institution,
        admin: User,
    ) -> None:
        await configure(db_session, institution, admin, test_settings)

        with capture_logs() as logs:
            await run_complete(db_session, test_settings, Provider(), text="Explain blood flow.")
            with pytest.raises(PersonalDataRefusedError):
                await run_complete(db_session, test_settings, Provider(), text="Mail a@b.org")

        text = json.dumps(logs, default=str)
        for secret in (KEY, "Explain blood flow", "blood", "a@b.org", "match"):
            assert secret not in text
        assert {entry["event"] for entry in logs} == {
            "ai_call",
            "ai_call_refused_personal_data",
        }
        call_log = next(e for e in logs if e["event"] == "ai_call")
        assert call_log["input_tokens"] == 1000

    async def test_a_provider_error_is_recorded_on_the_run_and_call(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        institution: Institution,
        admin: User,
    ) -> None:
        await configure(db_session, institution, admin, test_settings)
        provider = Provider(500, {"type": "error", "error": {"message": "overloaded"}})

        with pytest.raises(ProviderError):
            await run_complete(db_session, test_settings, provider)

        run = await db_session.scalar(select(AIRun))
        call = await db_session.scalar(select(AIRunCall))
        assert run is not None
        assert call is not None
        assert run.status is AIRunStatus.FAILED
        assert "500" in (run.error_message or "")
        assert call.response is None
        assert "overloaded" in (call.error_message or "")

    async def test_extra_calls_join_the_runs_they_belong_to(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        institution: Institution,
        admin: User,
    ) -> None:
        await configure(db_session, institution, admin, test_settings, max_calls_per_run=2)
        run = AIRun(
            type=AIRunType.MAPPING,
            status=AIRunStatus.RUNNING,
            provider="anthropic",
            model="m",
            prompt_version="compare:3",
        )
        db_session.add(run)
        await db_session.flush()
        provider = Provider()

        async def call() -> ai_gateway.GatewayResult:
            return await ai_gateway.complete(
                db_session,
                test_settings,
                template=TEMPLATE,
                fields={"objective_text": "Explain blood flow."},
                run_type=AIRunType.MAPPING,
                actor_id=None,
                run=run,
                transport=provider.transport,
            )

        await call()
        await call()
        with pytest.raises(AIBudgetExceededError, match="limit of 2 calls"):
            await call()

        assert len(provider.requests) == 2
        assert run.input_tokens == 2000
        assert run.status is AIRunStatus.RUNNING  # the caller finishes its own run


class TestPrivacyGuardInTheGateway:
    async def test_personal_data_is_refused_and_not_sent_or_stored(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        institution: Institution,
        admin: User,
    ) -> None:
        await configure(db_session, institution, admin, test_settings)
        provider = Provider()

        with pytest.raises(PersonalDataRefusedError) as error:
            await run_complete(db_session, test_settings, provider, text="Ask jane@example.org")

        assert provider.requests == []
        assert "jane@example.org" not in str(error.value)
        run = await db_session.scalar(select(AIRun))
        assert run is not None
        assert run.status is AIRunStatus.FAILED
        assert "jane@example.org" not in (run.error_message or "")
        assert "1 email" in (run.error_message or "")
        assert await db_session.scalar(select(AIRunCall.id)) is None

    async def test_the_names_of_this_installations_users_are_refused(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        institution: Institution,
        admin: User,
    ) -> None:
        await configure(db_session, institution, admin, test_settings)
        provider = Provider()

        with pytest.raises(PersonalDataRefusedError):
            await run_complete(db_session, test_settings, provider, text="Taught by Pat Admin")

        assert provider.requests == []

    async def test_redact_mode_sends_the_redacted_text_and_stores_what_was_sent(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        institution: Institution,
        admin: User,
    ) -> None:
        await configure(db_session, institution, admin, test_settings, on_personal_data="redact")
        provider = Provider()

        await run_complete(db_session, test_settings, provider, text="Ask jane@example.org now")

        sent = provider.requests[0].content.decode()
        assert "jane@example.org" not in sent
        assert "[email removed]" in sent
        call = await db_session.scalar(select(AIRunCall))
        assert call is not None
        assert "jane" not in json.dumps(call.request)
        assert call.request["redactions"] == {"email": 1}

    async def test_a_field_outside_the_allow_list_is_refused(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        institution: Institution,
        admin: User,
    ) -> None:
        await configure(db_session, institution, admin, test_settings)
        provider = Provider()

        with pytest.raises(PrivacyViolationError):
            await ai_gateway.complete(
                db_session,
                test_settings,
                template=TEMPLATE,
                fields={"objective_text": "x", "student_name": "Sam"},
                run_type=AIRunType.MAPPING,
                actor_id=None,
                transport=provider.transport,
            )

        assert provider.requests == []


class TestBudgets:
    async def seed_usage(
        self, db: AsyncSession, *, calls: int = 1, tokens: int = 10, cost: str = "0"
    ) -> None:
        run = AIRun(
            type=AIRunType.MAPPING,
            status=AIRunStatus.SUCCEEDED,
            provider="anthropic",
            model="m",
            prompt_version="t:1",
            estimated_cost=Decimal(cost),
        )
        db.add(run)
        await db.flush()
        for _ in range(calls):
            db.add(AIRunCall(run_id=run.id, request={}, input_tokens=tokens, output_tokens=0))
        await db.flush()

    @pytest.mark.parametrize(
        ("limits", "usage", "message"),
        [
            ({"monthly_call_cap": 3}, {"calls": 3}, "limit of 3 AI calls"),
            ({"monthly_token_cap": 100}, {"calls": 1, "tokens": 100}, "limit of 100 AI tokens"),
            ({"monthly_cost_cap": "5.00"}, {"cost": "5.00"}, "cost limit of USD 5.00"),
        ],
    )
    async def test_each_limit_refuses_with_a_clear_message(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        institution: Institution,
        admin: User,
        limits: dict[str, Any],
        usage: dict[str, Any],
        message: str,
    ) -> None:
        await configure(db_session, institution, admin, test_settings, **limits)
        await self.seed_usage(db_session, **usage)
        provider = Provider()

        with pytest.raises(AIBudgetExceededError, match=message) as error:
            await run_complete(db_session, test_settings, provider)

        assert "resets on" in str(error.value)
        assert provider.requests == []
        refused = await db_session.scalar(
            select(AIRun).where(AIRun.status == AIRunStatus.BUDGET_EXCEEDED)
        )
        assert refused is not None
        assert message in (refused.error_message or "")

    async def test_a_limit_of_none_means_no_limit(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        institution: Institution,
        admin: User,
    ) -> None:
        await configure(
            db_session,
            institution,
            admin,
            test_settings,
            monthly_call_cap=None,
            monthly_token_cap=None,
            monthly_cost_cap=None,
        )
        await self.seed_usage(db_session, calls=50, tokens=10**9, cost="100000")

        result = await run_complete(db_session, test_settings, Provider())

        assert result.text == "match"

    async def test_usage_from_last_month_does_not_count(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        institution: Institution,
        admin: User,
    ) -> None:
        from datetime import UTC, datetime

        from app.services import ai_budget

        await configure(db_session, institution, admin, test_settings, monthly_call_cap=1)
        await self.seed_usage(db_session, calls=1)

        now = datetime.now(UTC)
        next_month = datetime(now.year + (now.month // 12), now.month % 12 + 1, 15, tzinfo=UTC)
        assert (await ai_budget.month_usage(db_session, next_month)).calls == 0
        assert (await ai_budget.month_usage(db_session, now)).calls == 1

    async def test_a_cost_limit_needs_prices_for_a_paid_provider(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        institution: Institution,
        admin: User,
    ) -> None:
        await configure(
            db_session,
            institution,
            admin,
            test_settings,
            providers={
                "anthropic": {
                    "model": "claude-sonnet-5-5",
                    "api_key": KEY,
                    "input_price_per_mtok": None,
                    "output_price_per_mtok": None,
                }
            },
        )
        provider = Provider()

        with pytest.raises(AIBudgetExceededError, match="no prices"):
            await run_complete(db_session, test_settings, provider)

        assert provider.requests == []

    async def test_a_local_provider_costs_nothing_and_needs_no_prices(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        institution: Institution,
        admin: User,
    ) -> None:
        await ai_settings.update_ai_settings(
            db_session,
            institution,
            actor_id=admin.id,
            box=SecretBox.from_settings(test_settings),
            change=AIUpdate.model_validate(
                {
                    "active_provider": "ollama",
                    "providers": {"ollama": {"model": "llama", "base_url": "http://ollama:11434"}},
                }
            ),
        )
        provider = Provider(
            body={"message": {"content": "match"}, "prompt_eval_count": 7, "eval_count": 3}
        )

        result = await run_complete(db_session, test_settings, provider)

        assert result.cost == Decimal(0)
        assert (result.input_tokens, result.output_tokens) == (7, 3)
        assert str(provider.requests[0].url) == "http://ollama:11434/api/chat"


class TestConnectionTest:
    async def test_returns_a_result_for_every_outcome(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        institution: Institution,
        admin: User,
    ) -> None:
        off = await ai_gateway.check_connection(db_session, test_settings, actor_id=admin.id)
        assert (off.ok, off.code) == (False, "ai_disabled")

        await configure(db_session, institution, admin, test_settings)
        provider = Provider()
        ok = await ai_gateway.check_connection(
            db_session, test_settings, actor_id=admin.id, transport=provider.transport
        )
        assert (ok.ok, ok.code, ok.provider) == (True, "ok", AIProviderKind.ANTHROPIC)
        sent = json.loads(provider.requests[0].content)
        assert sent["max_tokens"] == ai_gateway.TEST_MAX_OUTPUT_TOKENS
        assert sent["messages"] == [{"role": "user", "content": prompts.CONNECTION_TEST.user}]


class TestEveryCallGoesThroughTheGuard:
    """Static checks: nothing but the gateway builds or uses a provider."""

    APP = Path(__file__).resolve().parent.parent / "app"

    def test_only_the_gateway_builds_providers(self) -> None:
        users = [
            path.relative_to(self.APP).as_posix()
            for path in self.APP.rglob("*.py")
            if re.search(r"\bbuild_provider\(", path.read_text(encoding="utf-8"))
        ]

        assert sorted(users) == ["ai/providers/__init__.py", "services/ai_gateway.py"]

    def test_only_the_ai_package_talks_to_provider_hosts(self) -> None:
        hosts = ("api.anthropic.com", "api.openai.com", "11434")
        outside = [
            path.relative_to(self.APP).as_posix()
            for path in self.APP.rglob("*.py")
            if "ai" not in path.relative_to(self.APP).parts[:1]
            and path.name != "ai_settings.py"
            and any(host in path.read_text(encoding="utf-8") for host in hosts)
        ]

        assert outside == []

    def test_adapters_take_only_guarded_requests(self) -> None:
        import inspect

        from app.ai.privacy import GuardedRequest
        from app.ai.providers import (
            anthropic,
            null,
            ollama,
            openai_compatible,
        )

        for module, cls in (
            (anthropic, anthropic.AnthropicProvider),
            (null, null.NullProvider),
            (ollama, ollama.OllamaProvider),
            (openai_compatible, openai_compatible.OpenAICompatibleProvider),
        ):
            parameters = inspect.signature(cls.generate_structured).parameters
            assert list(parameters) == ["self", "request"], module.__name__
            assert parameters["request"].annotation is GuardedRequest

    def test_the_data_location_enum_is_complete(self) -> None:
        assert {d.value for d in DataLocation} == {"local", "south_africa", "outside_south_africa"}
        assert {a.value for a in PersonalDataAction} == {"refuse", "redact"}
