"""Monthly usage and budget limits for AI calls (ADR 042).

Usage is read from the AI run and call records (the calendar month, UTC): calls and tokens
from ``ai_run_calls`` (a refused or failed attempt that reached a provider counts), cost
from ``ai_runs.estimated_cost``. A limit of ``None`` means no limit. A refusal names the
limit and says when it resets.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.errors import AIBudgetExceededError
from app.models import AIRun, AIRunCall
from app.models.ai_settings import AIProviderConfig, AISettings, DataLocation


@dataclass(frozen=True)
class Usage:
    period_start: datetime
    period_end: datetime
    calls: int
    tokens: int
    cost: Decimal


def month_bounds(now: datetime) -> tuple[datetime, datetime]:
    start = datetime(now.year, now.month, 1, tzinfo=UTC)
    end = (
        datetime(now.year + 1, 1, 1, tzinfo=UTC)
        if now.month == 12
        else datetime(now.year, now.month + 1, 1, tzinfo=UTC)
    )
    return start, end


async def month_usage(db: AsyncSession, now: datetime | None = None) -> Usage:
    now = now or datetime.now(UTC)
    start, end = month_bounds(now)
    calls, tokens = (
        await db.execute(
            select(
                func.count(AIRunCall.id),
                func.coalesce(func.sum(AIRunCall.input_tokens + AIRunCall.output_tokens), 0),
            ).where(AIRunCall.created_at >= start, AIRunCall.created_at < end)
        )
    ).one()
    cost = await db.scalar(
        select(func.coalesce(func.sum(AIRun.estimated_cost), 0)).where(
            AIRun.created_at >= start, AIRun.created_at < end
        )
    )
    return Usage(start, end, int(calls), int(tokens), Decimal(cost or 0))


def estimate_cost(config: AIProviderConfig, input_tokens: int, output_tokens: int) -> Decimal:
    """Cost in US dollars from the prices the admin entered (zero for a local provider)."""
    if config.data_location is DataLocation.LOCAL:
        return Decimal(0)
    price_in = config.input_price_per_mtok or Decimal(0)
    price_out = config.output_price_per_mtok or Decimal(0)
    return (price_in * input_tokens + price_out * output_tokens) / Decimal(1_000_000)


def budget_refusal(
    settings: AISettings,
    config: AIProviderConfig,
    usage: Usage,
    *,
    run_calls: int = 0,
) -> str | None:
    """Why a call must not be made now, or None."""
    resets = usage.period_end.strftime("%d %B %Y")
    if run_calls >= settings.max_calls_per_run:
        return f"This run has reached its limit of {settings.max_calls_per_run} calls."
    cap = settings.monthly_call_cap
    if cap is not None and usage.calls >= cap:
        return f"The monthly limit of {cap} AI calls is reached. It resets on {resets}."
    cap_tokens = settings.monthly_token_cap
    if cap_tokens is not None and usage.tokens >= cap_tokens:
        return f"The monthly limit of {cap_tokens} AI tokens is reached. It resets on {resets}."
    cap_cost = settings.monthly_cost_cap
    if cap_cost is not None:
        unpriced = (
            config.data_location is not DataLocation.LOCAL
            and config.input_price_per_mtok is None
            and config.output_price_per_mtok is None
        )
        if unpriced:
            return (
                "A monthly cost limit is set but this provider has no prices, so cost cannot "
                "be counted. Enter its prices or remove the cost limit."
            )
        if usage.cost >= cap_cost:
            return f"The monthly cost limit of USD {cap_cost} is reached. It resets on {resets}."
    return None


def check_budget(
    settings: AISettings, config: AIProviderConfig, usage: Usage, *, run_calls: int = 0
) -> None:
    """Raise ``AIBudgetExceededError`` when a limit is reached."""
    reason = budget_refusal(settings, config, usage, run_calls=run_calls)
    if reason:
        raise AIBudgetExceededError(reason)
