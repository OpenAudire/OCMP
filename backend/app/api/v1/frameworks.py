"""Frameworks: removing an unused framework version (ADR 037).

Needs ``frameworks.manage`` for the whole instance. Importing is in ``framework_packs``.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import require_permission
from app.core.database import DbSession
from app.core.permissions import Permission
from app.models import Framework, User
from app.services import frameworks as frameworks_service
from app.services.audit import audit_operation

router = APIRouter(prefix="/frameworks", tags=["frameworks"])

FrameworkManager = Annotated[User, Depends(require_permission(Permission.FRAMEWORKS_MANAGE))]


@router.delete("/{framework_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_framework(
    framework_id: uuid.UUID, actor: FrameworkManager, db: DbSession
) -> Response:
    """Delete a framework version that no objective is mapped to (409 otherwise). The
    framework is hidden, not erased, and the audit log keeps the entry."""
    framework = await db.get(Framework, framework_id)
    if framework is None or framework.is_deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Framework not found.")
    with audit_operation("framework.delete", actor_id=actor.id):
        await frameworks_service.delete_framework(db, framework)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
