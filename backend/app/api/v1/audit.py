"""Reading the audit log."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select

from app.api.deps import require_permission
from app.core.database import DbSession
from app.core.permissions import Permission
from app.models import AuditLog, User
from app.models.audit import ActorType

router = APIRouter(prefix="/audit-log", tags=["audit"])

AuditReader = Annotated[User, Depends(require_permission(Permission.AUDIT_VIEW))]


class AuditEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    occurred_at: datetime
    actor_type: ActorType
    actor_id: uuid.UUID | None
    entity_type: str
    entity_id: uuid.UUID | None
    action: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    context: dict[str, Any]


class AuditPage(BaseModel):
    items: list[AuditEntryRead]
    total: int


@router.get("", response_model=AuditPage)
async def list_audit_entries(
    _reader: AuditReader,
    db: DbSession,
    entity_type: Annotated[str | None, Query(max_length=64)] = None,
    entity_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    action: Annotated[str | None, Query(max_length=32)] = None,
    since: datetime | None = None,
    until: datetime | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AuditPage:
    """Audit entries, newest first, filtered by entity, actor, action and time."""
    query = select(AuditLog)
    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
    if entity_id:
        query = query.where(AuditLog.entity_id == entity_id)
    if actor_id:
        query = query.where(AuditLog.actor_id == actor_id)
    if action:
        query = query.where(AuditLog.action == action)
    if since:
        query = query.where(AuditLog.occurred_at >= since)
    if until:
        query = query.where(AuditLog.occurred_at < until)

    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    result = await db.execute(query.order_by(AuditLog.seq.desc()).offset(offset).limit(limit))
    return AuditPage(
        items=[AuditEntryRead.model_validate(e) for e in result.scalars()], total=int(total or 0)
    )
