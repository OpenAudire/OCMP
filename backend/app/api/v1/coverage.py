"""The coverage report and the gap report (Slice 1.21, ADR 050).

Both need ``reports.view`` at the version's programme (or at a module of it, for a narrower
view), and show only the part of the version the
user's roles show (ADR 027): the answer says so when that is only part. A version the user cannot
see is a 404. Only accepted links count; links accepted in bulk and links that need a re-check
are flagged, never hidden.
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from app.api.deps import CurrentUser
from app.api.v1.curriculum import Access
from app.core.database import DbSession
from app.models import Framework
from app.models.curriculum import ObjectiveLevel, VersionStatus
from app.models.framework import FrameworkStatus
from app.services import coverage_report
from app.services.authorization import AuthorizationError
from app.services.coverage_engine import ItemResult, Method, Status
from app.services.coverage_report import Report
from app.services.curriculum_read import VisibleVersion, visible_version
from app.services.policies import CoveragePolicy, coverage_policy_for_version
from app.services.report_access import may_report

router = APIRouter(tags=["coverage"])


class FrameworkRef(BaseModel):
    id: uuid.UUID
    name: str
    version_label: str


class VersionRef(BaseModel):
    id: uuid.UUID
    academic_year: int
    status: VersionStatus
    programme_code: str
    programme_name: str


class ParamsRead(BaseModel):
    multiple_match_n: int
    subordinate_min_percent: int
    weighted_low_percent: int


class Meta(BaseModel):
    framework: FrameworkRef
    version: VersionRef
    method: Method
    # The method in words, with this institution's numbers in it.
    definition: str
    params: ParamsRead
    generated_at: datetime
    # The user sees only part of the version: the figures cover only that part.
    partial: bool
    objectives_in_scope: int


class ItemRow(BaseModel):
    id: uuid.UUID
    code: str
    title: str
    parent_id: uuid.UUID | None
    depth: int
    is_leaf: bool
    leaves: int
    leaves_covered: int | None
    links: int
    bulk_links: int
    imported_links: int
    recheck_links: int
    waiting: int
    objectives: int
    value: float
    status: Status
    only_bulk: bool
    only_imported: bool


class MethodFigureRead(BaseModel):
    # The method's headline: a share of items (single, multiple), the average over groups
    # (subordinate) or the degree of coverage (weighted); null when there is nothing to average.
    headline: float | None
    # What the counts count: "items" or "groups".
    unit: str
    total: int
    covered: int
    partial: int
    uncovered: int


class SummaryRead(BaseModel):
    leaves: int
    groups: int
    methods: dict[Method, MethodFigureRead]
    links: int
    # Accepted links made directly to a group: shown apart, not counted in any figure.
    group_links: int
    bulk_links: int
    imported_links: int
    recheck_links: int
    waiting_links: int


class ColumnRead(BaseModel):
    key: str
    # "phase", "programme" (programme outcomes) or "none" (modules without a phase).
    kind: str
    label: str


class HeatRow(BaseModel):
    id: uuid.UUID
    code: str
    title: str
    # The share (0 to 1) in each column, and "all" for every column together.
    cells: dict[str, float]


class CoverageRead(Meta):
    summary: SummaryRead
    items: list[ItemRow]
    columns: list[ColumnRead]
    heatmap: list[HeatRow]


class PathItem(BaseModel):
    id: uuid.UUID
    code: str
    title: str


class GapRow(BaseModel):
    id: uuid.UUID
    code: str
    title: str
    path: list[PathItem]
    status: Status
    value: float
    links: int
    waiting: int
    reason: str
    leaves: int
    leaves_covered: int | None


class UnmappedRead(BaseModel):
    id: uuid.UUID
    text: str
    level: ObjectiveLevel
    module_id: uuid.UUID | None
    module_code: str | None
    event_id: uuid.UUID | None
    event_title: str | None
    waiting: int


class GapsRead(Meta):
    gaps: list[GapRow]
    # Groups under the share set for subordinate match (empty for the other methods).
    group_gaps: list[GapRow]
    unlinked: list[UnmappedRead]
    only_waiting: list[UnmappedRead]
    unlinked_total: int
    only_waiting_total: int


def _meta(report: Report, visible: VisibleVersion, policy: CoveragePolicy) -> Meta:
    return Meta(
        framework=FrameworkRef(
            id=report.framework.id,
            name=report.framework.name,
            version_label=report.framework.version_label,
        ),
        version=VersionRef(
            id=visible.version.id,
            academic_year=visible.version.academic_year,
            status=visible.version.status,
            programme_code=visible.programme.code,
            programme_name=visible.programme.name,
        ),
        method=report.method,
        definition=report.definition,
        params=ParamsRead(
            multiple_match_n=policy.multiple_match_n,
            subordinate_min_percent=policy.subordinate_min_percent,
            weighted_low_percent=policy.weighted_low_percent,
        ),
        generated_at=report.generated_at,
        partial=report.partial,
        objectives_in_scope=report.objectives_in_scope,
    )


def _row(result: ItemResult) -> ItemRow:
    item = result.item
    return ItemRow(
        id=item.id,
        code=item.code,
        title=item.title,
        parent_id=item.parent_id,
        depth=item.depth,
        is_leaf=result.is_leaf,
        leaves=result.leaves,
        leaves_covered=result.leaves_covered,
        links=result.links,
        bulk_links=result.bulk_links,
        imported_links=result.imported_links,
        recheck_links=result.recheck_links,
        waiting=result.waiting,
        objectives=result.objectives,
        value=round(result.value, 4),
        status=result.status,
        only_bulk=result.only_bulk,
        only_imported=result.only_imported,
    )


async def _allowed(
    db: DbSession,
    access: Access,
    actor: CurrentUser,
    version_id: uuid.UUID,
    framework_id: uuid.UUID,
) -> tuple[VisibleVersion, Framework, CoveragePolicy]:
    visible = await visible_version(db, access, version_id)
    if visible is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Curriculum version not found.")
    if not await may_report(db, actor, visible):
        raise AuthorizationError("You do not have permission to see reports for this programme.")
    framework = await db.get(Framework, framework_id)
    if framework is None or framework.is_deleted or framework.status == FrameworkStatus.DRAFT:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Framework not found.")
    return visible, framework, await coverage_policy_for_version(db, version_id)


def _gap_row(g: coverage_report.Gap) -> GapRow:
    return GapRow(
        id=g.result.item.id,
        code=g.result.item.code,
        title=g.result.item.title,
        path=[PathItem(id=p.id, code=p.code, title=p.title) for p in g.path],
        status=g.result.status,
        value=round(g.result.value, 4),
        links=g.result.links,
        waiting=g.result.waiting,
        reason=g.reason,
        leaves=g.result.leaves,
        leaves_covered=g.result.leaves_covered,
    )


@router.get("/curriculum-versions/{version_id}/coverage", response_model=CoverageRead)
async def coverage(
    version_id: uuid.UUID,
    access: Access,
    actor: CurrentUser,
    db: DbSession,
    framework_id: Annotated[uuid.UUID, Query()],
    method: Method = Method.SINGLE,
) -> CoverageRead:
    """How well a framework is covered by the accepted links of this version, by one of four
    labelled methods, with a heatmap of framework groups by phase."""
    visible, framework, policy = await _allowed(db, access, actor, version_id, framework_id)
    report = await coverage_report.build_report(db, visible, framework, method, policy)
    summary = report.summary
    return CoverageRead(
        **_meta(report, visible, policy).model_dump(),
        summary=SummaryRead(
            leaves=summary.leaves,
            groups=summary.groups,
            methods={
                m: MethodFigureRead(
                    headline=None if f.headline is None else round(f.headline, 4),
                    unit=f.unit,
                    total=f.total,
                    covered=f.covered,
                    partial=f.partial,
                    uncovered=f.uncovered,
                )
                for m, f in summary.methods.items()
            },
            links=summary.links,
            group_links=summary.group_links,
            bulk_links=summary.bulk_links,
            imported_links=summary.imported_links,
            recheck_links=summary.recheck_links,
            waiting_links=summary.waiting_links,
        ),
        items=[_row(r) for r in report.rows],
        columns=[ColumnRead(key=c.key, kind=c.kind, label=c.label) for c in report.columns],
        heatmap=[
            HeatRow(
                id=group.id,
                code=group.code,
                title=group.title,
                cells={k: round(v, 4) for k, v in report.grid[group.id].items()},
            )
            for group in report.tree.groups()
        ],
    )


@router.get("/curriculum-versions/{version_id}/coverage/gaps", response_model=GapsRead)
async def gaps(
    version_id: uuid.UUID,
    access: Access,
    actor: CurrentUser,
    db: DbSession,
    framework_id: Annotated[uuid.UUID, Query()],
    method: Method = Method.SINGLE,
) -> GapsRead:
    """Framework items with no or low coverage, and objectives with no accepted mapping."""
    visible, framework, policy = await _allowed(db, access, actor, version_id, framework_id)
    found = await coverage_report.build_gaps(db, visible, framework, method, policy)

    def unmapped(rows: list[coverage_report.UnmappedObjective]) -> list[UnmappedRead]:
        return [UnmappedRead(**vars(r)) for r in rows]

    return GapsRead(
        **_meta(found.report, visible, policy).model_dump(),
        gaps=[_gap_row(g) for g in found.gaps],
        group_gaps=[_gap_row(g) for g in found.group_gaps],
        unlinked=unmapped(found.unlinked),
        only_waiting=unmapped(found.only_waiting),
        unlinked_total=found.unlinked_total,
        only_waiting_total=found.only_waiting_total,
    )
