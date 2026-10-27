"""The one door to an AI provider (ADR 042).

``complete`` checks, in order: AI is on, local-only mode, the outside-South-Africa
acknowledgement, the stored key; then the privacy guard (the call is refused, not sent, when
personal data is found); then the budget; then it calls the provider and records the run and
call. Nothing outside this module may call a provider adapter.

Logs hold ids and counts only: never prompts, answers, keys or names.
"""

import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import prompts
from app.ai.confirmation import ConfirmationReceipt
from app.ai.errors import (
    AIAcknowledgementMissingError,
    AIBudgetExceededError,
    AIDisabledError,
    AIError,
    AILocalOnlyError,
    AINotConfiguredError,
    PersonalDataRefusedError,
    ProviderError,
)
from app.ai.privacy import GuardedRequest, PromptTemplate, load_known_names, prepare
from app.ai.providers import ProviderConfig, build_provider
from app.core.config import Settings
from app.core.logging import get_logger
from app.core.secrets import SecretBox, SecretUnreadableError
from app.models import AIRun, AIRunCall
from app.models.ai_settings import AIProviderConfig, AIProviderKind, AISettings, DataLocation
from app.models.mapping import AIRunStatus, AIRunType
from app.services import ai_budget, ai_settings
from app.services.institution_settings import get_institution

logger = get_logger(__name__)

TEST_MAX_OUTPUT_TOKENS = 200


@dataclass(frozen=True)
class GatewayResult:
    text: str
    input_tokens: int
    output_tokens: int
    cost: Decimal
    duration_ms: int
    run_id: uuid.UUID
    call_id: uuid.UUID
    provider: AIProviderKind
    model: str


@dataclass(frozen=True)
class ConnectionTestResult:
    ok: bool
    code: str
    message: str
    provider: AIProviderKind
    model: str | None
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0


@dataclass(frozen=True)
class _Plan:
    """The checked configuration a call will use."""

    row: AISettings
    kind: AIProviderKind
    config: AIProviderConfig
    provider_config: ProviderConfig


async def _plan(db: AsyncSession, settings: Settings) -> _Plan:
    """Checks that need no content: raises a refusal before anything is built or sent."""
    institution = await get_institution(db)
    row = await ai_settings.get_settings_row(db, institution) if institution else None
    if institution is None or row is None or row.active_provider is AIProviderKind.NULL:
        raise AIDisabledError
    kind = row.active_provider
    configs = await ai_settings.load_configs(db, institution)
    config = configs.get(kind)
    box = SecretBox.from_settings(settings)
    missing = ai_settings.missing_fields(kind, config, box)
    if config is None or missing:
        raise AINotConfiguredError(
            f"The {kind.value} provider is not complete (missing: {', '.join(missing)})."
        )
    if row.local_only and config.data_location is not DataLocation.LOCAL:
        raise AILocalOnlyError
    if config.data_location is DataLocation.OUTSIDE_SOUTH_AFRICA and not (
        ai_settings.is_acknowledged(row, kind, config)
    ):
        raise AIAcknowledgementMissingError
    try:
        api_key = ai_settings.read_key(config, box)
    except SecretUnreadableError as exc:
        raise AINotConfiguredError(f"The stored API key cannot be used: {exc}") from None
    return _Plan(
        row=row,
        kind=kind,
        config=config,
        provider_config=ProviderConfig(
            model=config.model or "",
            base_url=ai_settings.effective_base_url(kind, config),
            api_key=api_key,
            temperature=float(config.temperature) if config.temperature is not None else None,
        ),
    )


async def _record_refusal(
    db: AsyncSession,
    plan: _Plan,
    template: PromptTemplate,
    run_type: AIRunType,
    actor_id: uuid.UUID | None,
    status: AIRunStatus,
    message: str,
) -> None:
    """Keep a trace that a call was refused. It holds counts and reasons, never content."""
    now = datetime.now(UTC)
    db.add(
        AIRun(
            type=run_type,
            status=status,
            provider=plan.kind.value,
            model=plan.config.model or "",
            prompt_version=f"{template.name}:{template.version}",
            started_at=now,
            finished_at=now,
            error_message=message[:1000],
            created_by_id=actor_id,
        )
    )
    await db.flush()


async def complete(
    db: AsyncSession,
    settings: Settings,
    *,
    template: PromptTemplate,
    fields: dict[str, str],
    run_type: AIRunType,
    actor_id: uuid.UUID | None,
    max_output_tokens: int | None = None,
    run: AIRun | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    study_guide_confirmation: ConfirmationReceipt | None = None,
) -> GatewayResult:
    """Make one guarded provider call and record it.

    With ``run`` the call is added to that run (the caller sets its final status);
    otherwise a run of one call is made and finished here.

    Raises:
        AIError: A refusal (``AIRefusedError`` subclasses; nothing was sent) or a
            ``ProviderError`` (the provider failed; the call is recorded).
    """
    plan = await _plan(db, settings)
    known_names = await load_known_names(db)
    try:
        guarded: GuardedRequest = prepare(
            template,
            fields,
            known_names=known_names,
            action=plan.row.on_personal_data,
            max_output_tokens=max_output_tokens or plan.row.max_output_tokens,
            temperature=plan.provider_config.temperature,
            study_guide_confirmation=study_guide_confirmation,
        )
    except PersonalDataRefusedError as exc:
        await _record_refusal(db, plan, template, run_type, actor_id, AIRunStatus.FAILED, str(exc))
        logger.warning(
            "ai_call_refused_personal_data",
            template=template.name,
            fields=len(exc.findings),
            pieces=sum(sum(c.values()) for c in exc.findings.values()),
            user_id=str(actor_id) if actor_id else None,
        )
        raise

    usage = await ai_budget.month_usage(db)
    run_calls = 0
    if run is not None:
        run_calls = (
            await db.scalar(select(func.count(AIRunCall.id)).where(AIRunCall.run_id == run.id))
        ) or 0
    try:
        ai_budget.check_budget(plan.row, plan.config, usage, run_calls=run_calls)
    except AIBudgetExceededError as exc:
        await _record_refusal(
            db, plan, template, run_type, actor_id, AIRunStatus.BUDGET_EXCEEDED, str(exc)
        )
        logger.warning("ai_call_refused_budget", template=template.name)
        raise

    provider = build_provider(plan.kind, plan.provider_config, transport)
    own_run = run is None
    if run is None:
        run = AIRun(
            type=run_type,
            status=AIRunStatus.RUNNING,
            provider=plan.kind.value,
            model=plan.config.model or "",
            prompt_version=f"{template.name}:{template.version}",
            parameters={
                "max_output_tokens": guarded.max_output_tokens,
                "temperature": guarded.temperature,
            },
            scope={"template": template.name},
            started_at=datetime.now(UTC),
            created_by_id=actor_id,
        )
        db.add(run)
        await db.flush()

    started = time.monotonic()
    try:
        completion = await provider.generate_structured(guarded)
    except ProviderError as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        call = AIRunCall(
            run_id=run.id,
            request=guarded.as_record(),
            duration_ms=duration_ms,
            error_message=str(exc),
            created_by_id=actor_id,
        )
        db.add(call)
        if own_run:
            run.status = AIRunStatus.FAILED
            run.finished_at = datetime.now(UTC)
            run.error_message = str(exc)[:1000]
        await db.flush()
        logger.warning(
            "ai_call_failed",
            run_id=str(run.id),
            provider=plan.kind.value,
            status_code=exc.status_code,
            duration_ms=duration_ms,
        )
        raise

    duration_ms = int((time.monotonic() - started) * 1000)
    cost = ai_budget.estimate_cost(plan.config, completion.input_tokens, completion.output_tokens)
    call = AIRunCall(
        run_id=run.id,
        request=guarded.as_record(),
        response=completion.text,
        input_tokens=completion.input_tokens,
        output_tokens=completion.output_tokens,
        duration_ms=duration_ms,
        created_by_id=actor_id,
    )
    db.add(call)
    run.input_tokens += completion.input_tokens
    run.output_tokens += completion.output_tokens
    run.estimated_cost = run.estimated_cost + cost
    if own_run:
        run.status = AIRunStatus.SUCCEEDED
        run.finished_at = datetime.now(UTC)
    await db.flush()
    logger.info(
        "ai_call",
        run_id=str(run.id),
        provider=plan.kind.value,
        input_tokens=completion.input_tokens,
        output_tokens=completion.output_tokens,
        duration_ms=duration_ms,
        user_id=str(actor_id) if actor_id else None,
    )
    return GatewayResult(
        text=completion.text,
        input_tokens=completion.input_tokens,
        output_tokens=completion.output_tokens,
        cost=cost,
        duration_ms=duration_ms,
        run_id=run.id,
        call_id=call.id,
        provider=plan.kind,
        model=completion.model,
    )


async def check_connection(
    db: AsyncSession,
    settings: Settings,
    *,
    actor_id: uuid.UUID,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ConnectionTestResult:
    """Send the fixed, harmless test prompt through the chosen provider.

    Only called when an admin clicks the button. The prompt is fixed text with no fields;
    refusals and provider errors come back as a result, not an exception.
    """
    kind = AIProviderKind.NULL
    model: str | None = None
    try:
        institution = await get_institution(db)
        row = await ai_settings.get_settings_row(db, institution) if institution else None
        if row is not None:
            kind = row.active_provider
            configs = await ai_settings.load_configs(db, institution) if institution else {}
            cfg = configs.get(kind)
            model = cfg.model if cfg else None
        result = await complete(
            db,
            settings,
            template=prompts.CONNECTION_TEST,
            fields={},
            run_type=AIRunType.CONNECTION_TEST,
            actor_id=actor_id,
            max_output_tokens=TEST_MAX_OUTPUT_TOKENS,
            transport=transport,
        )
    except AIError as exc:
        return ConnectionTestResult(
            ok=False, code=exc.code, message=str(exc), provider=kind, model=model
        )
    return ConnectionTestResult(
        ok=True,
        code="ok",
        message="The provider answered.",
        provider=result.provider,
        model=result.model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        duration_ms=result.duration_ms,
    )
