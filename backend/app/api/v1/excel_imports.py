"""Excel imports of tags and mappings, and the import job history (Slice 1.26, ADR 055).

They work like the curriculum import (ADR 054): a template, a preview that writes nothing (the dry
run) and, for a valid file, a token that applies exactly that file in one transaction after
checking it again. Tags are instance-wide and need ``taglists.manage``; mappings go into a draft
version and need ``mapping.edit`` at the programme. The framework import is in
``framework_packs`` (the workbook becomes a pack). The history lists applied imports of every kind.
"""

import base64
import json
import secrets
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import select

from app.api.deps import (
    CurrentUser,
    RedisDep,
    SettingsDep,
    require_permission,
    too_many_attempts,
)
from app.api.v1.curriculum import Access
from app.api.v1.curriculum_import import XLSX, ApplyIn, ApplyRead, PreviewRead, preview_of
from app.api.v1.framework_packs import _read_body
from app.core.database import DbSession
from app.core.permissions import Permission, ScopeType
from app.models import CurriculumVersion, ImportJob, Programme, User
from app.services import mapping_import, rate_limit, tag_import
from app.services.audit import audit_operation
from app.services.authorization import (
    AuthorizationError,
    InvalidRequestError,
    ScopeRef,
    has_permission,
)
from app.services.curriculum_read import VisibleVersion, visible_version
from app.services.import_fields import Lists, build_workbook
from app.services.import_fields_data import MAPPING_HOW, MAPPING_SHEETS, TAG_HOW, TAG_SHEETS

router = APIRouter(tags=["import"])

TokenKind = str
TOKEN_SECONDS = 30 * 60
PREVIEWS_PER_MINUTE = 20
_SCOPE = "import-preview"
TagManager = Annotated[User, Depends(require_permission(Permission.TAGLISTS_MANAGE))]


def _key(kind: TokenKind, token: str) -> str:
    return f"excel-import:{kind}:{token}"


async def _limit(redis: Redis, actor: User) -> None:
    limited = await rate_limit.check(redis, _SCOPE, str(actor.id), PREVIEWS_PER_MINUTE)
    if not limited.allowed:
        raise too_many_attempts(limited.retry_after_seconds)
    await rate_limit.hit(redis, _SCOPE, str(actor.id), 60)


async def _store(redis: Redis, kind: TokenKind, actor: User, scope: str, body: bytes) -> str:
    token = secrets.token_urlsafe(24)
    await redis.set(
        _key(kind, token),
        json.dumps(
            {"user": str(actor.id), "scope": scope, "data": base64.b64encode(body).decode("ascii")}
        ),
        ex=TOKEN_SECONDS,
    )
    return token


async def _load(redis: Redis, kind: TokenKind, token: str, actor: User, scope: str) -> bytes:
    raw = await redis.get(_key(kind, token))
    stored = json.loads(raw) if raw else None
    if not stored or stored.get("user") != str(actor.id) or stored.get("scope") != scope:
        raise InvalidRequestError("The preview has expired. Upload the file and preview it again.")
    return base64.b64decode(stored["data"])


# --- Tags -------------------------------------------------------------------------------------


@router.get("/imports/tags/template")
async def tags_template(_actor: TagManager) -> Response:
    """The Excel template for tag lists and their tags."""
    return Response(
        build_workbook(
            Lists(),
            sheets=TAG_SHEETS,
            heading="Tag lists and tags: Excel template",
            how=TAG_HOW,
        ),
        media_type=XLSX,
        headers={"Content-Disposition": 'attachment; filename="tags-template.xlsx"'},
    )


@router.post("/imports/tags/preview", response_model=PreviewRead)
async def tags_preview(
    request: Request, actor: TagManager, db: DbSession, redis: RedisDep, settings: SettingsDep
) -> PreviewRead:
    """Check the workbook (the request body) and say what importing it would do. Writes nothing."""
    await _limit(redis, actor)
    limit = settings.pack_max_upload_mb * 1024 * 1024
    body = await _read_body(request, limit)
    plan = await tag_import.check(db, body, max_bytes=limit)
    token = await _store(redis, "tags", actor, "instance", body) if plan.valid else None
    return preview_of(plan, token)


@router.post("/imports/tags/apply", response_model=ApplyRead)
async def tags_apply(
    body: ApplyIn, actor: TagManager, db: DbSession, redis: RedisDep, settings: SettingsDep
) -> ApplyRead:
    """Carry out a previewed tag import in one transaction (the file is checked again first)."""
    content = await _load(redis, "tags", body.token, actor, "instance")
    plan = await tag_import.check(db, content, max_bytes=settings.pack_max_upload_mb * 1024 * 1024)
    if not plan.valid:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "The tags changed since the preview and the file now has problems. Preview it again.",
        )
    with audit_operation("import.tags", actor_id=actor.id):
        job_id = await tag_import.apply(db, plan, actor)
    await redis.delete(_key("tags", body.token))
    return ApplyRead(counts=plan.counts(), job_id=job_id)


# --- Mappings ---------------------------------------------------------------------------------


async def _mapping_target(
    db: DbSession, access: Access, actor: User, version_id: uuid.UUID
) -> VisibleVersion:
    visible = await visible_version(db, access, version_id)
    if visible is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Curriculum version not found.")
    scope = ScopeRef(ScopeType.PROGRAMME, visible.programme.id)
    if not await has_permission(db, actor, Permission.MAPPING_EDIT, scope):
        raise AuthorizationError("You may not import mappings into this programme's curriculum.")
    return visible


@router.get("/curriculum-versions/{version_id}/import/mappings/template")
async def mappings_template(
    version_id: uuid.UUID, access: Access, actor: CurrentUser, db: DbSession
) -> Response:
    """The Excel template for mapping links."""
    await _mapping_target(db, access, actor, version_id)
    return Response(
        build_workbook(
            Lists(),
            sheets=MAPPING_SHEETS,
            heading="Mappings: Excel template",
            how=MAPPING_HOW,
        ),
        media_type=XLSX,
        headers={"Content-Disposition": 'attachment; filename="mappings-template.xlsx"'},
    )


@router.post(
    "/curriculum-versions/{version_id}/import/mappings/preview", response_model=PreviewRead
)
async def mappings_preview(
    version_id: uuid.UUID,
    request: Request,
    access: Access,
    actor: CurrentUser,
    db: DbSession,
    redis: RedisDep,
    settings: SettingsDep,
) -> PreviewRead:
    """Check the workbook (the request body) and say what importing it would do. Writes nothing."""
    visible = await _mapping_target(db, access, actor, version_id)
    await _limit(redis, actor)
    limit = settings.pack_max_upload_mb * 1024 * 1024
    body = await _read_body(request, limit)
    plan = await mapping_import.check(db, visible.version, body, max_bytes=limit)
    token = await _store(redis, "mappings", actor, str(version_id), body) if plan.valid else None
    return preview_of(plan, token)


class MappingApplyIn(ApplyIn):
    # The links were already reviewed elsewhere: accept them (method "imported") instead of
    # suggesting them. Needs permission to review mappings.
    decided: bool = False


@router.post("/curriculum-versions/{version_id}/import/mappings/apply", response_model=ApplyRead)
async def mappings_apply(
    version_id: uuid.UUID,
    body: MappingApplyIn,
    access: Access,
    actor: CurrentUser,
    db: DbSession,
    redis: RedisDep,
    settings: SettingsDep,
) -> ApplyRead:
    """Make the suggested links of a previewed file in one transaction (checked again first)."""
    visible = await _mapping_target(db, access, actor, version_id)
    if body.decided and not await has_permission(
        db, actor, Permission.MAPPING_REVIEW, ScopeRef(ScopeType.PROGRAMME, visible.programme.id)
    ):
        raise AuthorizationError("Only someone who may review mappings can record them as decided.")
    content = await _load(redis, "mappings", body.token, actor, str(version_id))
    plan = await mapping_import.check(
        db, visible.version, content, max_bytes=settings.pack_max_upload_mb * 1024 * 1024
    )
    if not plan.valid:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "The mappings changed since the preview and the file now has problems. "
            "Preview it again.",
        )
    with audit_operation("import.mappings", actor_id=actor.id):
        job_id = await mapping_import.apply(db, visible.version, plan, actor, decided=body.decided)
    await redis.delete(_key("mappings", body.token))
    return ApplyRead(counts=plan.counts(), job_id=job_id)


# --- History ----------------------------------------------------------------------------------


class ImportJobRead(BaseModel):
    id: uuid.UUID
    kind: str
    status: str
    created_at: str
    by: str | None
    programme_code: str | None
    academic_year: int | None
    counts: dict[str, dict[str, int]]


@router.get("/import-jobs", response_model=list[ImportJobRead])
async def list_import_jobs(
    actor: CurrentUser, db: DbSession, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> list[ImportJobRead]:
    """Applied imports, newest first: your own, or everyone's with permission to read the audit
    log. They hold counts only, never the file or any cell."""
    query = (
        select(ImportJob, User, Programme.code, CurriculumVersion.academic_year)
        .outerjoin(User, User.id == ImportJob.created_by_id)
        .outerjoin(CurriculumVersion, CurriculumVersion.id == ImportJob.version_id)
        .outerjoin(Programme, Programme.id == CurriculumVersion.programme_id)
        .order_by(ImportJob.created_at.desc())
        .limit(limit)
    )
    if not await has_permission(db, actor, Permission.AUDIT_VIEW):
        query = query.where(ImportJob.created_by_id == actor.id)
    return [
        ImportJobRead(
            id=job.id,
            kind=job.kind,
            status=job.status,
            created_at=job.created_at.isoformat(),
            by=user.display_name if user else None,
            programme_code=code,
            academic_year=year,
            counts=job.summary,
        )
        for job, user, code, year in (await db.execute(query)).all()
    ]
