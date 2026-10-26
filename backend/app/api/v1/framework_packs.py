"""Framework pack import (ADR 036): upload, check and preview, then confirm.

Needs ``frameworks.manage`` for the whole instance (a pack that carries tag lists also
needs ``taglists.manage``). The upload is read as the raw request body, capped by
``PACK_MAX_UPLOAD_MB``. A valid preview keeps the file in Redis for 30 minutes under a
random token tied to the user, so confirming does not upload it again.
"""

import json
import secrets
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import FileResponse

from app.api.deps import RedisDep, SettingsDep, require_permission, too_many_attempts
from app.core.database import DbSession
from app.core.permissions import Permission
from app.models import User
from app.schemas.framework_packs import (
    PackCountsRead,
    PackImportRead,
    PackImportRequest,
    PackMetadataRead,
    PackPreviewRead,
    PackTemplateRead,
    ProblemRead,
    SampleItemRead,
)
from app.services import rate_limit
from app.services.audit import audit_operation
from app.services.authorization import InvalidRequestError, has_permission
from app.services.frameworks import activate_framework
from app.services.packs import (
    FrameworkPack,
    PackProblem,
    check_pack,
    import_pack,
    resolve_pack,
    tree_order,
)

router = APIRouter(prefix="/framework-packs", tags=["framework-packs"])

FrameworkManager = Annotated[User, Depends(require_permission(Permission.FRAMEWORKS_MANAGE))]

TOKEN_SECONDS = 30 * 60
SAMPLE_ITEMS = 200
PREVIEWS_PER_MINUTE = 20
_SCOPE = "pack-preview"
TEMPLATES = Path(__file__).resolve().parents[2] / "pack_templates"


def _redis_key(token: str) -> str:
    return f"pack-import:{token}"


async def _read_body(request: Request, limit: int) -> bytes:
    too_big = HTTPException(
        status.HTTP_413_CONTENT_TOO_LARGE,
        f"The file is larger than {limit // (1024 * 1024)} MB, the limit for this installation.",
    )
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit:
        raise too_big
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > limit:
            raise too_big
    return bytes(body)


def _parse(text: str) -> tuple[FrameworkPack | None, list[PackProblem]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, [
            PackProblem(
                "",
                f"The file is not valid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno}).",
            )
        ]
    return check_pack(data)


def _decode(body: bytes) -> tuple[str | None, list[PackProblem]]:
    if not body.strip():
        return None, [PackProblem("", "The file is empty.")]
    try:
        return body.decode("utf-8-sig"), []
    except UnicodeDecodeError:
        return None, [PackProblem("", "The file is not UTF-8 text. Save it as UTF-8 JSON.")]


async def _all_problems(
    db: DbSession,
    user: User,
    pack: FrameworkPack,
    max_items: int,
) -> tuple[list[PackProblem], list[str]]:
    problems: list[PackProblem] = []
    warnings: list[str] = []
    if len(pack.items) > max_items:
        problems.append(
            PackProblem(
                "items",
                f"The pack has {len(pack.items)} items; this installation accepts "
                f"{max_items} (PACK_MAX_ITEMS).",
            )
        )
    if pack.metadata.template:
        problems.append(
            PackProblem(
                "metadata.template",
                "This is a blank template. Replace the placeholder text and remove "
                '"template": true from the metadata, then upload it again.',
            )
        )
    if pack.tag_lists and not await has_permission(db, user, Permission.TAGLISTS_MANAGE):
        problems.append(
            PackProblem(
                "tag_lists", "This pack has tag lists; you need permission to manage tag lists."
            )
        )
    if not problems:
        resolution = await resolve_pack(db, pack)
        problems += resolution.problems
        warnings += resolution.warnings
    return problems, warnings


def _problem_reads(problems: list[PackProblem]) -> list[ProblemRead]:
    return [ProblemRead(path=p.path, message=p.message) for p in problems]


@router.post("/preview", response_model=PackPreviewRead)
async def preview_pack(
    request: Request,
    actor: FrameworkManager,
    db: DbSession,
    redis: RedisDep,
    settings: SettingsDep,
) -> PackPreviewRead:
    """Check a pack file (the request body, JSON) and say what importing it would do.

    Problems in the file come back as 200 with ``valid: false`` and a list of errors;
    only a file over the size limit is refused (413).
    """
    limited = await rate_limit.check(redis, _SCOPE, str(actor.id), PREVIEWS_PER_MINUTE)
    if not limited.allowed:
        raise too_many_attempts(limited.retry_after_seconds)
    await rate_limit.hit(redis, _SCOPE, str(actor.id), 60)

    body = await _read_body(request, settings.pack_max_upload_mb * 1024 * 1024)
    text, problems = _decode(body)
    pack: FrameworkPack | None = None
    warnings: list[str] = []
    if text is not None:
        pack, problems = _parse(text)
    if pack is not None:
        problems, warnings = await _all_problems(db, actor, pack, settings.pack_max_items)
    if pack is None or text is None:
        return PackPreviewRead(valid=False, errors=_problem_reads(problems), warnings=[])

    ordered = tree_order(pack)
    meta = pack.metadata
    values = sum(len(t.values) for t in pack.tag_lists)
    counts = PackCountsRead(
        items=len(pack.items),
        levels=max((depth for _, depth in ordered), default=-1) + 1,
        root_items=sum(1 for item in pack.items if item.parent_code is None),
        cross_references=len(pack.cross_references),
        external_references=sum(1 for r in pack.cross_references if r.to_framework),
        crosswalks=len(pack.crosswalks),
        crosswalk_entries=sum(len(c.entries) for c in pack.crosswalks),
        taxonomy_scales=len(pack.taxonomy_scales),
        tag_lists=len(pack.tag_lists),
        tag_values=values,
    )
    token = None
    if not problems:
        token = secrets.token_urlsafe(24)
        await redis.set(
            _redis_key(token), json.dumps({"user": str(actor.id), "data": text}), ex=TOKEN_SECONDS
        )
    return PackPreviewRead(
        valid=not problems,
        errors=_problem_reads(problems),
        warnings=warnings,
        format_version=pack.format_version,
        metadata=PackMetadataRead(**meta.model_dump()),
        counts=counts,
        sample=[
            SampleItemRead(code=item.code, title=item.title, depth=depth)
            for item, depth in ordered[:SAMPLE_ITEMS]
        ],
        sample_truncated=len(ordered) > SAMPLE_ITEMS,
        token=token,
        expires_in=TOKEN_SECONDS if token else None,
    )


@router.post("/import", response_model=PackImportRead, status_code=status.HTTP_201_CREATED)
async def import_checked_pack(
    body: PackImportRequest,
    actor: FrameworkManager,
    db: DbSession,
    redis: RedisDep,
    settings: SettingsDep,
) -> PackImportRead:
    """Import the pack of a valid preview. 404 if the preview expired or is not yours;
    the pack is checked again against the database (409 if the version appeared meanwhile)."""
    stored = await redis.get(_redis_key(body.token))
    payload = json.loads(stored) if stored else None
    if payload is None or payload["user"] != str(actor.id):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "This preview has expired. Upload the file again."
        )
    pack, problems = _parse(payload["data"])
    if pack is not None:
        problems, _ = await _all_problems(db, actor, pack, settings.pack_max_items)
    if pack is None or problems:
        raise InvalidRequestError(
            "Invalid framework pack: " + "; ".join(str(p) for p in problems[:10])
        )

    meta = pack.metadata
    with audit_operation(
        "framework.import", actor_id=actor.id, reason=f"Pack {meta.key} version {meta.version}"
    ):
        result = await import_pack(db, pack, created_by_id=actor.id)
        superseded: list[uuid.UUID] = []
        if body.activate:
            superseded = await activate_framework(db, result.framework)
    await redis.delete(_redis_key(body.token))
    summary = result.summary
    framework = result.framework
    return PackImportRead(
        framework_id=framework.id,
        key=framework.key,
        name=framework.name,
        version=framework.version_label,
        status=framework.status,
        items=summary.items,
        cross_references=summary.cross_references,
        external_references=summary.external_references,
        crosswalks=summary.crosswalks,
        crosswalk_entries=summary.crosswalk_entries,
        scales_created=summary.scales_created,
        tag_lists_created=summary.tag_lists_created,
        tag_values_added=summary.tag_values_added,
        superseded_versions=len(superseded),
    )


def _template_files() -> dict[str, Path]:
    return {path.stem: path for path in sorted(TEMPLATES.glob("*.json"))}


@router.get("/templates", response_model=list[PackTemplateRead])
async def list_templates(actor: FrameworkManager) -> list[PackTemplateRead]:
    """The blank, structure-only templates that ship with the application."""
    out = []
    for name, path in _template_files().items():
        data = json.loads(path.read_text(encoding="utf-8"))
        meta = data["metadata"]
        out.append(
            PackTemplateRead(
                name=name,
                title=meta["name"],
                description=meta.get("description", ""),
                items=len(data["items"]),
            )
        )
    return out


@router.get("/templates/{name}")
async def download_template(name: str, actor: FrameworkManager) -> Response:
    """Download a template as a JSON file."""
    path = _template_files().get(name)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found.")
    return FileResponse(
        path,
        media_type="application/json",
        filename=f"{name}.json",
        content_disposition_type="attachment",
    )
