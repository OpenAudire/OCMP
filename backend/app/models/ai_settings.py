"""AI provider settings: which provider, budgets, privacy mode, encrypted keys (ADR 041, 042)."""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import ClassVar

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Audited, CoreModel, str_enum


class AIProviderKind(StrEnum):
    NULL = "null"  # AI off: the whole platform works without it
    ANTHROPIC = "anthropic"
    OPENAI_COMPATIBLE = "openai_compatible"
    OLLAMA = "ollama"


class DataLocation(StrEnum):
    """Where a provider processes the text it is sent (declared by the admin, ADR 042)."""

    LOCAL = "local"  # this server or the institution's own network
    SOUTH_AFRICA = "south_africa"
    OUTSIDE_SOUTH_AFRICA = "outside_south_africa"


class PersonalDataAction(StrEnum):
    """What the privacy guard does when it finds personal data in a prompt."""

    REFUSE = "refuse"  # the call is not made
    REDACT = "redact"  # replaced with placeholders, then the call is made


class AISettings(Audited, CoreModel):
    """The institution's AI policy. One row per institution; the default is AI off."""

    __tablename__ = "ai_settings"
    __table_args__ = (
        CheckConstraint(
            "(monthly_cost_cap IS NULL OR monthly_cost_cap >= 0)"
            " AND (monthly_token_cap IS NULL OR monthly_token_cap >= 0)"
            " AND (monthly_call_cap IS NULL OR monthly_call_cap >= 0)"
            " AND max_calls_per_run > 0 AND max_output_tokens > 0",
            name="limits_valid",
        ),
    )

    institution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"), unique=True
    )
    active_provider: Mapped[AIProviderKind] = mapped_column(
        str_enum(AIProviderKind, "ai_active_provider"),
        default=AIProviderKind.NULL,
        server_default=AIProviderKind.NULL.value,
    )
    # Restrictive defaults: only local providers until an admin turns this off.
    local_only: Mapped[bool] = mapped_column(default=True, server_default="true")
    on_personal_data: Mapped[PersonalDataAction] = mapped_column(
        str_enum(PersonalDataAction, "ai_personal_data_action"),
        default=PersonalDataAction.REFUSE,
        server_default=PersonalDataAction.REFUSE.value,
    )
    # Caps per calendar month (UTC); NULL means no cap.
    monthly_cost_cap: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), default=Decimal("10.00"), server_default="10.00"
    )
    monthly_token_cap: Mapped[int | None] = mapped_column(
        BigInteger, default=2_000_000, server_default="2000000"
    )
    monthly_call_cap: Mapped[int | None] = mapped_column(
        Integer, default=2000, server_default="2000"
    )
    max_calls_per_run: Mapped[int] = mapped_column(Integer, default=500, server_default="500")
    max_output_tokens: Mapped[int] = mapped_column(Integer, default=1024, server_default="1024")
    # The admin's acknowledgement that text goes outside South Africa, for one provider setup.
    ack_provider_key: Mapped[str | None] = mapped_column(String(600), default=None)
    ack_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    ack_at: Mapped[datetime | None] = mapped_column(default=None)


class AIProviderConfig(Audited, CoreModel):
    """Settings of one provider, including its encrypted API key.

    The key is never returned by the API and never written to the audit log (the change
    is recorded by column name only).
    """

    __tablename__ = "ai_provider_configs"
    __audit_exclude__: ClassVar[frozenset[str]] = frozenset({"api_key_encrypted"})
    __table_args__ = (
        UniqueConstraint("institution_id", "provider"),
        CheckConstraint("provider <> 'null'", name="provider_is_real"),
        CheckConstraint("temperature IS NULL OR temperature BETWEEN 0 AND 2", name="temperature"),
        CheckConstraint(
            "(input_price_per_mtok IS NULL OR input_price_per_mtok >= 0)"
            " AND (output_price_per_mtok IS NULL OR output_price_per_mtok >= 0)",
            name="prices_positive",
        ),
    )

    institution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[AIProviderKind] = mapped_column(str_enum(AIProviderKind, "ai_provider_kind"))
    model: Mapped[str | None] = mapped_column(String(128), default=None)
    base_url: Mapped[str | None] = mapped_column(String(512), default=None)
    data_location: Mapped[DataLocation] = mapped_column(
        str_enum(DataLocation, "ai_data_location"),
        default=DataLocation.OUTSIDE_SOUTH_AFRICA,
        server_default=DataLocation.OUTSIDE_SOUTH_AFRICA.value,
    )
    temperature: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), default=None)
    # US dollars per million tokens, entered by the admin (prices change; none are built in).
    input_price_per_mtok: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), default=None)
    output_price_per_mtok: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), default=None)
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, default=None)
    api_key_set_at: Mapped[datetime | None] = mapped_column(default=None)
