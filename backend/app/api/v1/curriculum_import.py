"""Excel import of a curriculum version's structure and objectives (Slice 1.25, ADR 054).

``GET .../import/template`` gives the Excel template; ``POST .../import/preview`` takes the
filled-in workbook as the raw request body, checks it and says what importing it would do (it writes
nothing: this is the dry run); ``POST .../import/apply`` carries out the previewed file, in one
transaction. A valid preview keeps the file in Redis for 30 minutes under a random token tied to the
user and the version, so applying does not upload it again, and the file is checked again against
the data as it is then. Needs ``curriculum.edit`` and ``objectives.edit`` at the programme; only
draft versions can be imported into; a version the person cannot see is a 404. The file is never
stored, and neither is its name.
"""

import base64
import json
import secrets
import uuid

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, RedisDep, SettingsDep, too_many_attempts
from app.api.v1.curriculum import Access
from app.api.v1.framework_packs import _read_body
from app.core.database import DbSession
from app.core.permissions import Permission, ScopeType
from app.jobs.embeddings import enqueue_objective
from app.models import User
from app.services import curriculum_import, rate_limit
from app.services.audit import audit_operation
from app.services.authorization import (
    AuthorizationError,
    InvalidRequestError,
    ScopeRef,
    has_permission,
)
from app.services.curriculum_read import VisibleVersion, visible_version
from app.services.import_fields import build_workbook
from app.services.institution_settings import get_institution, parse_settings

router = APIRouter(tags=["import"])

TOKEN_SECONDS = 30 * 60
PREVIEWS_PER_MINUTE = 20
LISTED_ROWS = 1000
_SCOPE = "import-preview"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _key(token: str) -> str:
    return f"curriculum-import:{token}"


class ProblemRead(BaseModel):
    sheet: str | None
    row: int | None
    column: str | None
    message: str


class RowRead(BaseModel):
    sheet: str
    row: int
    external_id: str
    action: str
    label: str
    changes: list[str]


class PreviewRead(BaseModel):
    valid: bool
    would_change: bool
    problems: list[ProblemRead]
    more_problems: int
    warnings: list[str]
    counts: dict[str, dict[str, int]]
    rows: list[RowRead]
    more_rows: int
    token: str | None


class ApplyIn(BaseModel):
    token: str = Field(min_length=8, max_length=200)


class ApplyRead(BaseModel):
    counts: dict[str, dict[str, int]]
    job_id: uuid.UUID


async def _target(
    db: DbSession, access: Access, actor: User, version_id: uuid.UUID
) -> VisibleVersion:
    visible = await visible_version(db, access, version_id)
    if visible is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Curriculum version not found.")
    scope = ScopeRef(ScopeType.PROGRAMME, visible.programme.id)
    for permission in (Permission.CURRICULUM_EDIT, Permission.OBJECTIVES_EDIT):
        if not await has_permission(db, actor, permission, scope):
            raise AuthorizationError("You may not import into this programme's curriculum.")
    return visible


async def _context(db: DbSession, visible: VisibleVersion) -> tuple[uuid.UUID, str | None]:
    institution = await get_institution(db)
    scale = parse_settings(institution.settings).default_taxonomy_scale if institution else None
    return visible.programme.faculty_id, scale


@router.get("/curriculum-versions/{version_id}/import/template")
async def download_template(
    version_id: uuid.UUID, access: Access, actor: CurrentUser, db: DbSession
) -> Response:
    """The Excel template, with the dropdowns of this institution (teaching formats, taxonomy)."""
    visible = await _target(db, access, actor, version_id)
    faculty_id, scale = await _context(db, visible)
    existing = await curriculum_import.load_existing(db, visible.version, faculty_id, scale)
    return Response(
        build_workbook(existing.lists()),
        media_type=XLSX,
        headers={"Content-Disposition": 'attachment; filename="curriculum-template.xlsx"'},
    )


def _preview(plan: curriculum_import.Plan, token: str | None) -> PreviewRead:
    return PreviewRead(
        valid=plan.valid,
        would_change=plan.changes,
        problems=[
            ProblemRead(sheet=p.sheet, row=p.row, column=p.column, message=p.message)
            for p in plan.problems
        ],
        more_problems=plan.truncated_problems,
        warnings=plan.warnings,
        counts=plan.counts(),
        rows=[
            RowRead(
                sheet=r.sheet,
                row=r.row,
                external_id=r.external_id,
                action=r.action,
                label=r.label,
                changes=r.changes,
            )
            for r in plan.rows[:LISTED_ROWS]
        ],
        more_rows=max(0, len(plan.rows) - LISTED_ROWS),
        token=token,
    )


@router.post("/curriculum-versions/{version_id}/import/preview", response_model=PreviewRead)
async def preview_import(
    version_id: uuid.UUID,
    request: Request,
    access: Access,
    actor: CurrentUser,
    db: DbSession,
    redis: RedisDep,
    settings: SettingsDep,
) -> PreviewRead:
    """Check the workbook (the request body) and say what importing it would do. Problems in the
    file come back as 200 with ``valid: false`` and a list; only a file over the size limit is
    refused (413). Nothing is written."""
    visible = await _target(db, access, actor, version_id)
    limited = await rate_limit.check(redis, _SCOPE, str(actor.id), PREVIEWS_PER_MINUTE)
    if not limited.allowed:
        raise too_many_attempts(limited.retry_after_seconds)
    await rate_limit.hit(redis, _SCOPE, str(actor.id), 60)

    limit = settings.pack_max_upload_mb * 1024 * 1024
    body = await _read_body(request, limit)
    faculty_id, scale = await _context(db, visible)
    plan = await curriculum_import.check(
        db,
        visible.version,
        body,
        max_bytes=limit,
        faculty_id=faculty_id,
        default_scale=scale,
    )
    token = None
    if plan.valid:
        token = secrets.token_urlsafe(24)
        await redis.set(
            _key(token),
            json.dumps(
                {
                    "user": str(actor.id),
                    "version": str(version_id),
                    "data": base64.b64encode(body).decode("ascii"),
                }
            ),
            ex=TOKEN_SECONDS,
        )
    return _preview(plan, token)


@router.post("/curriculum-versions/{version_id}/import/apply", response_model=ApplyRead)
async def apply_import(
    version_id: uuid.UUID,
    body: ApplyIn,
    access: Access,
    actor: CurrentUser,
    db: DbSession,
    redis: RedisDep,
    settings: SettingsDep,
) -> ApplyRead:
    """Carry out a previewed import, in one transaction. The file is checked again first; if the
    curriculum changed so that it now has problems, nothing is applied (409)."""
    visible = await _target(db, access, actor, version_id)
    raw = await redis.get(_key(body.token))
    stored = json.loads(raw) if raw else None
    if (
        not stored
        or stored.get("user") != str(actor.id)
        or stored.get("version") != str(version_id)
    ):
        raise InvalidRequestError("The preview has expired. Upload the file and preview it again.")
    content = base64.b64decode(stored["data"])
    faculty_id, scale = await _context(db, visible)
    limit = settings.pack_max_upload_mb * 1024 * 1024
    plan = await curriculum_import.check(
        db,
        visible.version,
        content,
        max_bytes=limit,
        faculty_id=faculty_id,
        default_scale=scale,
    )
    if not plan.valid:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "The curriculum changed since the preview and the file now has problems. "
            "Preview it again.",
        )
    existing = await curriculum_import.load_existing(db, visible.version, faculty_id, scale)
    can_approve = await has_permission(
        db,
        actor,
        Permission.OBJECTIVES_APPROVE,
        ScopeRef(ScopeType.PROGRAMME, visible.programme.id),
    )
    with audit_operation("import.curriculum", actor_id=actor.id):
        applied = await curriculum_import.apply(
            db, visible.version, plan, existing, actor, can_approve=can_approve
        )
    await redis.delete(_key(body.token))
    for objective_id in applied.objective_ids:
        enqueue_objective(settings, objective_id)
    return ApplyRead(counts=applied.summary, job_id=applied.job_id)
