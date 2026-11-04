"""Exports of a curriculum version (Slice 1.27, ADR 056): the full round-trip workbook, the
objectives x framework items matrix and the JSON of the whole version.

Like the reports, they need ``reports.view`` and ``curriculum.view`` at the programme (or at a
module for a narrower view) and contain only what the person's roles show of the version (ADR 027);
a version they cannot see is a 404. The round-trip workbook is for the whole version only. File
names are fixed and never contain user text. At most 20 exports a minute for each user.
"""

import json
import uuid

from fastapi import APIRouter, HTTPException, Response, status

from app.api.deps import CurrentUser, RedisDep, too_many_attempts
from app.api.v1.curriculum import Access
from app.core.database import DbSession
from app.core.logging import get_logger
from app.models import Framework
from app.models.framework import FrameworkStatus
from app.services import curriculum_export, rate_limit
from app.services.authorization import AuthorizationError, InvalidRequestError
from app.services.curriculum_read import VisibleVersion, visible_version
from app.services.report_access import may_export

router = APIRouter(tags=["export"])
logger = get_logger(__name__)

_SCOPE = "version-export"
EXPORTS_PER_MINUTE = 20
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


async def _target(
    db: DbSession, access: Access, actor: CurrentUser, redis: RedisDep, version_id: uuid.UUID
) -> VisibleVersion:
    visible = await visible_version(db, access, version_id)
    if visible is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Curriculum version not found.")
    if not await may_export(db, actor, visible):
        raise AuthorizationError("You do not have permission to export this programme.")
    limited = await rate_limit.check(redis, _SCOPE, str(actor.id), EXPORTS_PER_MINUTE)
    if not limited.allowed:
        raise too_many_attempts(limited.retry_after_seconds)
    await rate_limit.hit(redis, _SCOPE, str(actor.id), 60)
    return visible


@router.get("/curriculum-versions/{version_id}/export/workbook")
async def export_workbook(
    version_id: uuid.UUID, access: Access, actor: CurrentUser, db: DbSession, redis: RedisDep
) -> Response:
    """The whole version in the sheets of the import templates, to edit and import back."""
    visible = await _target(db, access, actor, redis, version_id)
    if not visible.view.full:
        raise AuthorizationError("The full export needs access to the whole curriculum version.")
    content = await curriculum_export.build_roundtrip(db, visible)
    logger.info("version_exported", user_id=str(actor.id), kind="workbook")
    return Response(
        content,
        media_type=XLSX,
        headers={"Content-Disposition": 'attachment; filename="curriculum-export.xlsx"'},
    )


@router.get("/curriculum-versions/{version_id}/export/matrix")
async def export_matrix(
    version_id: uuid.UUID,
    access: Access,
    actor: CurrentUser,
    db: DbSession,
    redis: RedisDep,
    framework_id: uuid.UUID,
) -> Response:
    """Objectives (rows) by the items of one framework (columns), with the coverage score of the
    accepted link in each cell."""
    visible = await _target(db, access, actor, redis, version_id)
    framework = await db.get(Framework, framework_id)
    if framework is None or framework.is_deleted or framework.status == FrameworkStatus.DRAFT:
        raise InvalidRequestError("That framework cannot be used for an export.")
    content = await curriculum_export.build_matrix(db, visible, framework)
    logger.info("version_exported", user_id=str(actor.id), kind="matrix")
    return Response(
        content,
        media_type=XLSX,
        headers={"Content-Disposition": 'attachment; filename="objectives-by-items.xlsx"'},
    )


@router.get("/curriculum-versions/{version_id}/export/json")
async def export_json(
    version_id: uuid.UUID, access: Access, actor: CurrentUser, db: DbSession, redis: RedisDep
) -> Response:
    """Everything the person sees of the version as one JSON document."""
    visible = await _target(db, access, actor, redis, version_id)
    document = await curriculum_export.build_json(db, visible)
    logger.info("version_exported", user_id=str(actor.id), kind="json")
    return Response(
        json.dumps(document, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="curriculum-version.json"'},
    )
