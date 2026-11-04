"""Reports as documents, and their export to Excel and PDF (Slice 1.22, ADR 051).

``GET /curriculum-versions/{id}/reports/{key}`` answers a report as tables; ``.../export`` answers
the same report as a workbook or a PDF. Both need ``reports.view`` at the programme (or at a module
for a narrower view) and show only what the person's roles show of the version (ADR 027); a version
they cannot see is a 404. Every sheet and page states the report's method and when it was made.
File names are fixed and never contain user text.
"""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel

from app.api.deps import CurrentUser, RedisDep, too_many_attempts
from app.api.v1.curriculum import Access
from app.core.database import DbSession
from app.core.logging import get_logger
from app.services import rate_limit, report_export
from app.services.authorization import AuthorizationError
from app.services.coverage_engine import Method
from app.services.curriculum_read import visible_version
from app.services.policies import coverage_policy_for_version
from app.services.report_access import may_report
from app.services.report_context import ReportContext
from app.services.report_export import ReportDoc
from app.services.report_registry import REPORTS

router = APIRouter(tags=["reports"])
logger = get_logger(__name__)

_SCOPE = "report-export"
EXPORTS_PER_MINUTE = 20


class AboutLine(BaseModel):
    label: str
    value: str


class ColumnRead(BaseModel):
    label: str
    kind: report_export.Kind


class SectionRead(BaseModel):
    title: str
    note: str
    columns: list[ColumnRead]
    rows: list[list[str | int | float | None]]


class ReportRead(BaseModel):
    key: str
    title: str
    method: str
    made_on: datetime
    about: list[AboutLine]
    sections: list[SectionRead]


def _read(doc: ReportDoc) -> ReportRead:
    return ReportRead(
        key=doc.key,
        title=doc.title,
        method=doc.method,
        made_on=doc.made_on,
        about=[AboutLine(label=label, value=value) for label, value in doc.about],
        sections=[
            SectionRead(
                title=s.title,
                note=s.note,
                columns=[ColumnRead(label=c.label, kind=c.kind) for c in s.columns],
                rows=s.rows,
            )
            for s in doc.sections
        ],
    )


async def _build(
    db: DbSession,
    access: Access,
    actor: CurrentUser,
    version_id: uuid.UUID,
    key: str,
    framework_id: uuid.UUID | None,
    method: Method,
    phase_id: uuid.UUID | None,
) -> ReportDoc:
    builder = REPORTS.get(key)
    if builder is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That report does not exist.")
    visible = await visible_version(db, access, version_id)
    if visible is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Curriculum version not found.")
    if not await may_report(db, actor, visible):
        raise AuthorizationError("You do not have permission to see reports for this programme.")
    context = ReportContext(
        db=db,
        visible=visible,
        policy=await coverage_policy_for_version(db, version_id),
        framework_id=framework_id,
        method=method,
        phase_id=phase_id,
    )
    return await builder(context)


@router.get("/curriculum-versions/{version_id}/reports/{key}", response_model=ReportRead)
async def get_report(
    version_id: uuid.UUID,
    key: str,
    access: Access,
    actor: CurrentUser,
    db: DbSession,
    framework_id: uuid.UUID | None = None,
    method: Method = Method.SINGLE,
    phase_id: uuid.UUID | None = None,
) -> ReportRead:
    """A report as tables, with how it was made."""
    return _read(await _build(db, access, actor, version_id, key, framework_id, method, phase_id))


@router.get("/curriculum-versions/{version_id}/reports/{key}/export")
async def export_report(
    version_id: uuid.UUID,
    key: str,
    access: Access,
    actor: CurrentUser,
    db: DbSession,
    redis: RedisDep,
    format: Annotated[Literal["xlsx", "pdf"], Query()],
    framework_id: uuid.UUID | None = None,
    method: Method = Method.SINGLE,
    phase_id: uuid.UUID | None = None,
) -> Response:
    """The same report as an Excel workbook or a PDF. Every sheet and page states the method and
    the time the report was made."""
    limited = await rate_limit.check(redis, _SCOPE, str(actor.id), EXPORTS_PER_MINUTE)
    if not limited.allowed:
        raise too_many_attempts(limited.retry_after_seconds)
    doc = await _build(db, access, actor, version_id, key, framework_id, method, phase_id)
    await rate_limit.hit(redis, _SCOPE, str(actor.id), 60)
    if format == "xlsx":
        content, media = report_export.to_xlsx(doc), report_export.XLSX
    else:
        content, media = report_export.to_pdf(doc), report_export.PDF
    logger.info("report_exported", user_id=str(actor.id), report=key, format=format)
    return Response(
        content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{key}-report.{format}"'},
    )
