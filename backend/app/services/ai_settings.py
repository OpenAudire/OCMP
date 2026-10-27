"""AI settings: provider choice, local-only mode, budgets, acknowledgement and encrypted keys.

Rules (ADR 042): the default is AI off with local-only mode on; a provider that processes
text outside South Africa needs an explicit acknowledgement before it can be chosen, and
the acknowledgement stops covering it when its address or location changes; local-only mode
refuses any provider that is not local; keys are written encrypted and never read back.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.locality import normalise_base_url
from app.ai.providers.anthropic import BASE_URL as ANTHROPIC_BASE_URL
from app.ai.providers.anthropic import SUGGESTED_MODELS as ANTHROPIC_MODELS
from app.core.secrets import SecretBox, SecretUnreadableError
from app.models import Institution
from app.models.ai_settings import AIProviderConfig, AIProviderKind, AISettings, DataLocation
from app.schemas.ai import (
    AcknowledgementRead,
    AISettingsRead,
    AIUpdate,
    BudgetRead,
    KeyStatus,
    ProviderRead,
    ProviderUpdate,
    StatusRead,
    UsageRead,
)
from app.services import ai_budget
from app.services.authorization import InvalidRequestError


@dataclass(frozen=True)
class ProviderInfo:
    """What the code knows about a kind of provider."""

    key_mode: str  # required | optional | none
    base_url_mode: str  # fixed | required
    default_base_url: str | None
    default_location: DataLocation
    fixed_location: DataLocation | None
    suggested_models: tuple[str, ...] = ()


PROVIDERS: dict[AIProviderKind, ProviderInfo] = {
    AIProviderKind.ANTHROPIC: ProviderInfo(
        key_mode="required",
        base_url_mode="fixed",
        default_base_url=ANTHROPIC_BASE_URL,
        default_location=DataLocation.OUTSIDE_SOUTH_AFRICA,
        fixed_location=DataLocation.OUTSIDE_SOUTH_AFRICA,
        suggested_models=ANTHROPIC_MODELS,
    ),
    AIProviderKind.OPENAI_COMPATIBLE: ProviderInfo(
        key_mode="optional",
        base_url_mode="required",
        default_base_url="https://api.openai.com/v1",
        default_location=DataLocation.OUTSIDE_SOUTH_AFRICA,
        fixed_location=None,
    ),
    AIProviderKind.OLLAMA: ProviderInfo(
        key_mode="none",
        base_url_mode="required",
        default_base_url=None,
        default_location=DataLocation.LOCAL,
        fixed_location=None,
    ),
}


async def get_settings_row(db: AsyncSession, institution: Institution) -> AISettings | None:
    return await db.scalar(select(AISettings).where(AISettings.institution_id == institution.id))


async def get_or_create_settings(db: AsyncSession, institution: Institution) -> AISettings:
    row = await get_settings_row(db, institution)
    if row is None:
        try:
            # Two first visits at once: the second finds the first one's row.
            async with db.begin_nested():
                row = AISettings(institution_id=institution.id)
                db.add(row)
                await db.flush()
        except IntegrityError:
            row = await get_settings_row(db, institution)
            assert row is not None
    return row


async def load_configs(
    db: AsyncSession, institution: Institution
) -> dict[AIProviderKind, AIProviderConfig]:
    result = await db.scalars(
        select(AIProviderConfig).where(AIProviderConfig.institution_id == institution.id)
    )
    return {c.provider: c for c in result}


def effective_base_url(kind: AIProviderKind, config: AIProviderConfig | None) -> str | None:
    """The address used: the stored one, or the provider's fixed address."""
    info = PROVIDERS[kind]
    if info.base_url_mode == "fixed":
        return info.default_base_url
    return (config.base_url if config else None) or None


def acknowledgement_key(kind: AIProviderKind, config: AIProviderConfig) -> str:
    """What an acknowledgement covers: the provider, its address and its location."""
    return f"{kind.value}|{effective_base_url(kind, config) or ''}|{config.data_location.value}"


def key_status(config: AIProviderConfig | None, box: SecretBox) -> KeyStatus:
    if config is None or not config.api_key_encrypted:
        return "not_set"
    try:
        box.decrypt(config.api_key_encrypted)
    except SecretUnreadableError:
        return "unreadable"
    return "set"


def missing_fields(
    kind: AIProviderKind, config: AIProviderConfig | None, box: SecretBox
) -> list[str]:
    """What must be filled in before the provider can be chosen."""
    info = PROVIDERS[kind]
    missing: list[str] = []
    if config is None or not config.model:
        missing.append("model")
    if info.base_url_mode == "required" and not effective_base_url(kind, config):
        missing.append("base_url")
    if info.key_mode == "required" and key_status(config, box) != "set":
        missing.append("api_key")
    return missing


def is_acknowledged(row: AISettings, kind: AIProviderKind, config: AIProviderConfig) -> bool:
    return row.ack_provider_key == acknowledgement_key(kind, config)


def read_key(config: AIProviderConfig, box: SecretBox) -> str | None:
    """The decrypted API key, for the moment of a call. Never returned by the API.

    Raises:
        SecretUnreadableError: If the stored key cannot be decrypted with the configured keys.
    """
    return box.decrypt(config.api_key_encrypted) if config.api_key_encrypted else None


def _apply_provider(
    kind: AIProviderKind,
    config: AIProviderConfig,
    change: ProviderUpdate,
    box: SecretBox,
    now: datetime,
) -> None:
    info = PROVIDERS[kind]
    sent = change.model_fields_set
    if "data_location" in sent and change.data_location is not None:
        if info.fixed_location and change.data_location != info.fixed_location:
            raise InvalidRequestError(f"The location of {kind.value} cannot be changed.")
        config.data_location = change.data_location
    if "model" in sent:
        config.model = (change.model or "").strip() or None
    if "base_url" in sent:
        if info.base_url_mode == "fixed":
            raise InvalidRequestError(f"The address of {kind.value} cannot be changed.")
        config.base_url = (change.base_url or "").strip() or None
    # Whenever the address or location changed, they must still agree.
    if config.base_url and info.base_url_mode != "fixed":
        config.base_url = normalise_base_url(config.base_url, config.data_location)
    for column in ("temperature", "input_price_per_mtok", "output_price_per_mtok"):
        if column in sent:
            setattr(config, column, getattr(change, column))
    if change.clear_api_key:
        config.api_key_encrypted = None
        config.api_key_set_at = None
    if change.api_key is not None:
        if info.key_mode == "none":
            raise InvalidRequestError(f"{kind.value} does not use an API key.")
        value = change.api_key.get_secret_value().strip()
        if not value:
            raise InvalidRequestError("The API key is empty.")
        config.api_key_encrypted = box.encrypt(value)
        config.api_key_set_at = now


async def update_ai_settings(
    db: AsyncSession,
    institution: Institution,
    *,
    actor_id: uuid.UUID,
    box: SecretBox,
    change: AIUpdate,
) -> AISettings:
    """Apply a settings change, checking the whole result.

    The change is made inside a savepoint: a refused change leaves nothing half-applied.

    Raises:
        InvalidRequestError: If the result breaks a rule (incomplete provider, local-only
            with a non-local provider, outside South Africa without acknowledgement, bad
            address).
    """
    async with db.begin_nested():
        return await _update(db, institution, actor_id=actor_id, box=box, change=change)


async def _update(
    db: AsyncSession,
    institution: Institution,
    *,
    actor_id: uuid.UUID,
    box: SecretBox,
    change: AIUpdate,
) -> AISettings:
    now = datetime.now(UTC)
    row = await get_or_create_settings(db, institution)
    configs = await load_configs(db, institution)
    sent = change.model_fields_set

    for kind, provider_change in (change.providers or {}).items():
        if kind is AIProviderKind.NULL:
            raise InvalidRequestError("The Null provider has no settings.")
        config = configs.get(kind)
        if config is None:
            config = AIProviderConfig(
                institution_id=institution.id,
                provider=kind,
                data_location=PROVIDERS[kind].default_location,
            )
            db.add(config)
            configs[kind] = config
        _apply_provider(kind, config, provider_change, box, now)

    if change.active_provider is not None:
        row.active_provider = change.active_provider
    if change.local_only is not None:
        row.local_only = change.local_only
    if change.on_personal_data is not None:
        row.on_personal_data = change.on_personal_data
    for name in ("monthly_cost_cap", "monthly_token_cap", "monthly_call_cap"):
        if name in sent:
            setattr(row, name, getattr(change, name))
    for name in ("max_calls_per_run", "max_output_tokens"):
        value = getattr(change, name)
        if value is not None:
            setattr(row, name, value)

    active = row.active_provider
    if active is AIProviderKind.NULL and row.ack_provider_key is not None:
        # Turning AI off withdraws the acknowledgement; choosing a provider outside South
        # Africa again needs a fresh one. The audit log keeps who acknowledged and when.
        row.ack_provider_key = None
        row.ack_by_id = None
        row.ack_at = None
    if active is not AIProviderKind.NULL:
        active_config = configs.get(active)
        missing = missing_fields(active, active_config, box)
        if missing or active_config is None:
            raise InvalidRequestError(
                f"Fill in the {active.value} settings first: {', '.join(missing or ['model'])}."
            )
        if row.local_only and active_config.data_location is not DataLocation.LOCAL:
            raise InvalidRequestError(
                "Local-only mode is on. Only a provider on this server or network can be "
                "chosen; turn local-only mode off to choose this one."
            )
        if active_config.data_location is DataLocation.OUTSIDE_SOUTH_AFRICA:
            if change.acknowledge_outside_south_africa:
                row.ack_provider_key = acknowledgement_key(active, active_config)
                row.ack_by_id = actor_id
                row.ack_at = now
            elif not is_acknowledged(row, active, active_config):
                raise InvalidRequestError(
                    "This provider processes text outside South Africa. Acknowledge that "
                    "before choosing it."
                )
    await db.flush()
    return row


def _provider_read(
    kind: AIProviderKind, config: AIProviderConfig | None, box: SecretBox
) -> ProviderRead:
    info = PROVIDERS[kind]
    location = config.data_location if config else info.default_location
    return ProviderRead(
        kind=kind,
        model=config.model if config else None,
        base_url=config.base_url if config and info.base_url_mode != "fixed" else None,
        data_location=location,
        data_location_fixed=info.fixed_location is not None,
        outside_south_africa=location is DataLocation.OUTSIDE_SOUTH_AFRICA,
        is_local=location is DataLocation.LOCAL,
        temperature=config.temperature if config else None,
        input_price_per_mtok=config.input_price_per_mtok if config else None,
        output_price_per_mtok=config.output_price_per_mtok if config else None,
        key_mode=info.key_mode,
        key_status=key_status(config, box),
        key_set_at=config.api_key_set_at if config else None,
        base_url_mode=info.base_url_mode,
        default_base_url=info.default_base_url,
        suggested_models=list(info.suggested_models),
        missing=missing_fields(kind, config, box),
    )


async def overview(db: AsyncSession, institution: Institution, box: SecretBox) -> AISettingsRead:
    """Everything the admin screen shows. Never includes a key."""
    row = await get_or_create_settings(db, institution)
    configs = await load_configs(db, institution)
    usage = await ai_budget.month_usage(db)
    active = row.active_provider
    config = configs.get(active) if active is not AIProviderKind.NULL else None

    reasons: list[str] = []
    budget_message: str | None = None
    if active is not AIProviderKind.NULL:
        if config is None or missing_fields(active, config, box):
            reasons.append("not_configured")
        else:
            if row.local_only and config.data_location is not DataLocation.LOCAL:
                reasons.append("local_only")
            if config.data_location is DataLocation.OUTSIDE_SOUTH_AFRICA and not is_acknowledged(
                row, active, config
            ):
                reasons.append("acknowledgement_missing")
            budget_message = ai_budget.budget_refusal(row, config, usage)
            if budget_message:
                reasons.append("budget_exceeded")
    state: Literal["off", "ready", "blocked"] = (
        "off" if active is AIProviderKind.NULL else ("blocked" if reasons else "ready")
    )
    return AISettingsRead(
        active_provider=active,
        local_only=row.local_only,
        on_personal_data=row.on_personal_data,
        budget=BudgetRead(
            monthly_cost_cap=row.monthly_cost_cap,
            monthly_token_cap=row.monthly_token_cap,
            monthly_call_cap=row.monthly_call_cap,
            max_calls_per_run=row.max_calls_per_run,
            max_output_tokens=row.max_output_tokens,
        ),
        acknowledgement=AcknowledgementRead(
            acknowledged_at=row.ack_at,
            current=bool(
                config is not None
                and active is not AIProviderKind.NULL
                and is_acknowledged(row, active, config)
            ),
        ),
        usage=UsageRead(
            period_start=usage.period_start,
            period_end=usage.period_end,
            calls=usage.calls,
            tokens=usage.tokens,
            cost=usage.cost,
        ),
        status=StatusRead(
            state=state,
            reasons=reasons,
            budget_message=budget_message,
        ),
        providers=[_provider_read(kind, configs.get(kind), box) for kind in PROVIDERS],
    )
