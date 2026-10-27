"""Schemas of the AI settings API. No schema ever carries an API key out."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.models.ai_settings import AIProviderKind, DataLocation, PersonalDataAction

KeyStatus = Literal["not_set", "set", "unreadable"]


class ProviderUpdate(BaseModel):
    """Changes to one provider. Fields left out are unchanged."""

    model_config = ConfigDict(extra="forbid")

    model: Annotated[str | None, Field(max_length=128)] = None
    base_url: Annotated[str | None, Field(max_length=512)] = None
    data_location: DataLocation | None = None
    temperature: Annotated[Decimal | None, Field(ge=0, le=2, decimal_places=2)] = None
    input_price_per_mtok: Annotated[Decimal | None, Field(ge=0, le=1_000_000)] = None
    output_price_per_mtok: Annotated[Decimal | None, Field(ge=0, le=1_000_000)] = None
    # Write-only. Stored encrypted; never returned.
    api_key: Annotated[SecretStr | None, Field(max_length=500)] = None
    clear_api_key: bool = False


class AIUpdate(BaseModel):
    """Changes to the AI settings. Fields left out are unchanged; a cap sent as null means none."""

    model_config = ConfigDict(extra="forbid")

    active_provider: AIProviderKind | None = None
    local_only: bool | None = None
    on_personal_data: PersonalDataAction | None = None
    monthly_cost_cap: Annotated[Decimal | None, Field(ge=0, le=1_000_000, decimal_places=2)] = None
    monthly_token_cap: Annotated[int | None, Field(ge=0, le=10**12)] = None
    monthly_call_cap: Annotated[int | None, Field(ge=0, le=10**9)] = None
    max_calls_per_run: Annotated[int | None, Field(ge=1, le=100_000)] = None
    max_output_tokens: Annotated[int | None, Field(ge=1, le=128_000)] = None
    # True records that the admin read the warning about text leaving South Africa.
    acknowledge_outside_south_africa: bool = False
    providers: dict[AIProviderKind, ProviderUpdate] | None = None


class ProviderRead(BaseModel):
    kind: AIProviderKind
    model: str | None
    base_url: str | None
    data_location: DataLocation
    # Anthropic is always treated as outside South Africa; the admin cannot change that.
    data_location_fixed: bool
    outside_south_africa: bool
    is_local: bool
    temperature: Decimal | None
    input_price_per_mtok: Decimal | None
    output_price_per_mtok: Decimal | None
    # Whether a key is needed, optional or not used.
    key_mode: Literal["required", "optional", "none"]
    key_status: KeyStatus
    key_set_at: datetime | None
    base_url_mode: Literal["fixed", "required"]
    default_base_url: str | None
    suggested_models: list[str]
    # What the admin has to fill in before this provider can be chosen.
    missing: list[str]


class AcknowledgementRead(BaseModel):
    acknowledged_at: datetime | None
    # Whether the acknowledgement still covers the chosen provider's address and location.
    current: bool


class UsageRead(BaseModel):
    period_start: datetime
    period_end: datetime
    calls: int
    tokens: int
    cost: Decimal


class BudgetRead(BaseModel):
    monthly_cost_cap: Decimal | None
    monthly_token_cap: int | None
    monthly_call_cap: int | None
    max_calls_per_run: int
    max_output_tokens: int


class StatusRead(BaseModel):
    """What would happen to a call now."""

    state: Literal["off", "ready", "blocked"]
    # Stable codes the screen turns into sentences: local_only, acknowledgement_missing,
    # budget_exceeded, not_configured.
    reasons: list[str]
    # The sentence to show when the budget is the reason (it says when the limit resets).
    budget_message: str | None = None


class EncryptionRead(BaseModel):
    """Whether API keys can be stored (ADR 041); never anything about the keys themselves."""

    # False in production while SECRETS_ENCRYPTION_KEYS is not set: saving a key is refused.
    keys_stored_ok: bool
    # Some stored key was sealed with another key than the newest: run rotate-secrets.
    rotation_needed: bool


class AISettingsRead(BaseModel):
    active_provider: AIProviderKind
    local_only: bool
    on_personal_data: PersonalDataAction
    budget: BudgetRead
    acknowledgement: AcknowledgementRead
    usage: UsageRead
    status: StatusRead
    providers: list[ProviderRead]
    encryption: EncryptionRead


class ConnectionTestRead(BaseModel):
    ok: bool
    # "ok" or a stable reason code (see app.ai.errors).
    code: str
    message: str
    provider: AIProviderKind
    model: str | None
    input_tokens: int
    output_tokens: int
    duration_ms: int
