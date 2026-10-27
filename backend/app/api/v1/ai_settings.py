"""Admin AI settings: provider, local-only mode, budgets, keys (write-only) and a test button.

Needs ``settings.manage``. Changes are audited; an API key is audited by column name only and
is never returned. The connection test sends one fixed, harmless prompt and only when called.
"""

from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import RedisDep, SettingsDep, require_permission, too_many_attempts
from app.core.database import DbSession
from app.core.permissions import Permission
from app.core.secrets import SecretBox
from app.models import Institution, User
from app.schemas.ai import AISettingsRead, AIUpdate, ConnectionTestRead
from app.services import ai_gateway, ai_settings, rate_limit
from app.services.audit import audit_operation, record_event
from app.services.institution_settings import get_institution

router = APIRouter(prefix="/ai", tags=["ai"])

SettingsManager = Annotated[User, Depends(require_permission(Permission.SETTINGS_MANAGE))]

TESTS_PER_MINUTE = 5
_TEST_SCOPE = "ai-test"


def ai_transport() -> httpx.AsyncBaseTransport | None:
    """The HTTP transport for provider calls; tests replace it with a mock."""
    return None


Transport = Annotated[httpx.AsyncBaseTransport | None, Depends(ai_transport)]


async def _institution(db: DbSession) -> Institution:
    institution = await get_institution(db)
    if institution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="The institution is not set up yet."
        )
    return institution


@router.get("/settings", response_model=AISettingsRead)
async def read_ai_settings(
    _admin: SettingsManager, db: DbSession, settings: SettingsDep
) -> AISettingsRead:
    """The AI settings, usage this month and what would happen to a call now."""
    institution = await _institution(db)
    return await ai_settings.overview(db, institution, SecretBox.from_settings(settings))


@router.patch("/settings", response_model=AISettingsRead)
async def change_ai_settings(
    body: AIUpdate, admin: SettingsManager, db: DbSession, settings: SettingsDep
) -> AISettingsRead:
    """Change the AI settings. API keys are write-only: send ``api_key``, never read it back."""
    institution = await _institution(db)
    box = SecretBox.from_settings(settings)
    with audit_operation("ai.settings_update", actor_id=admin.id):
        await ai_settings.update_ai_settings(
            db, institution, actor_id=admin.id, box=box, change=body
        )
    return await ai_settings.overview(db, institution, box)


@router.post("/test-connection", response_model=ConnectionTestRead)
async def test_ai_connection(
    admin: SettingsManager,
    db: DbSession,
    settings: SettingsDep,
    redis: RedisDep,
    transport: Transport,
) -> ConnectionTestRead:
    """Send one fixed, harmless prompt through the chosen provider (no curriculum data)."""
    limited = await rate_limit.check(redis, _TEST_SCOPE, str(admin.id), TESTS_PER_MINUTE)
    if not limited.allowed:
        raise too_many_attempts(limited.retry_after_seconds)
    await rate_limit.hit(redis, _TEST_SCOPE, str(admin.id), 60)
    with audit_operation("ai.connection_test", actor_id=admin.id):
        result = await ai_gateway.check_connection(
            db, settings, actor_id=admin.id, transport=transport
        )
        await record_event(
            db,
            action="connection_test",
            entity_type="ai_settings",
            details={"ok": result.ok, "code": result.code, "provider": result.provider.value},
        )
    return ConnectionTestRead(
        ok=result.ok,
        code=result.code,
        message=result.message,
        provider=result.provider,
        model=result.model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        duration_ms=result.duration_ms,
    )
