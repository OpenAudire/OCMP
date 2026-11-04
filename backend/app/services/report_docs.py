"""The reports as documents (Slice 1.22, ADR 051): the coverage report and the gap report turned
into the tables that the screens, the Excel export and the PDF export share. New reports (1.23,
1.24) are added here as builders and registered in ``api/v1/reports.py``.

Labels are English: exports are not translated yet (see ADR 051).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Framework
from app.models.framework import FrameworkStatus
from app.services import coverage_report
from app.services.authorization import InvalidRequestError
from app.services.coverage_engine import Method, Status
from app.services.coverage_report import GapReport, Report
from app.services.curriculum_read import VisibleVersion
from app.services.policies import CoveragePolicy
from app.services.report_export import Column, Kind, ReportDoc, Section

METHOD_NAMES: dict[Method, str] = {
    Method.SINGLE: "Single match",
    Method.MULTIPLE: "Multiple match",
    Method.SUBORDINATE: "Subordinate match",
    Method.WEIGHTED: "Weighted content coverage",
}
STATUS_NAMES: dict[Status, str] = {
    Status.COVERED: "Covered",
    Status.PARTIAL: "Partial",
    Status.NONE: "Not covered",
}
LEVEL_NAMES = {
    "programme": "Programme outcome",
    "module": "Module outcome",
    "learning_event": "Session",
}


@dataclass
class ReportContext:
    """What a report builder needs: the database, what the user may see, the institution's
    numbers and the choices made on the screen."""

    db: AsyncSession
    visible: VisibleVersion
    policy: CoveragePolicy
    framework_id: uuid.UUID | None = None
    method: Method = Method.SINGLE
    phase_id: uuid.UUID | None = None

    async def framework(self) -> Framework:
        if self.framework_id is None:
            raise InvalidRequestError("Choose a framework for this report.")
        framework = await self.db.get(Framework, self.framework_id)
        if framework is None or framework.is_deleted or framework.status == FrameworkStatus.DRAFT:
            raise InvalidRequestError("That framework cannot be used for a report.")
        return framework


Builder = Callable[[ReportContext], Awaitable[ReportDoc]]


def common_about(
    visible: VisibleVersion, made_on_text: str, partial: bool
) -> list[tuple[str, str]]:
    version = visible.version
    lines = [
        (
            "Curriculum version",
            f"{visible.programme.code} {visible.programme.name}, {version.academic_year} "
            f"({version.status.value})",
        ),
        ("Made on", made_on_text),
        (
            "What is counted",
            "Only accepted mapping links count, for the objectives you may see. Suggestions and "
            "links waiting for review are shown apart; links accepted in bulk and links that "
            "need a re-check are counted and flagged.",
        ),
    ]
    if partial:
        lines.append(
            (
                "Only part of the curriculum",
                "This report covers only the part of the curriculum "
                "the person who made it can see.",
            )
        )
    return lines


def _numbers(report: Report | GapReport) -> str:
    base = report.report if isinstance(report, GapReport) else report
    p = base.policy
    return (
        f"Items needed for multiple match: {p.multiple_match_n}. Groups listed in the gap report "
        f"under {p.subordinate_min_percent}% (subordinate match). Items listed under "
        f"{p.weighted_low_percent}% (weighted coverage)."
    )


def coverage_doc(report: Report, visible: VisibleVersion) -> ReportDoc:
    name = METHOD_NAMES[report.method]
    made = report.generated_at.strftime("%Y-%m-%d %H:%M UTC")
    about = [
        ("Report", "Coverage report"),
        ("Method", f"{name}. {report.definition}"),
        ("Framework", f"{report.framework.name} ({report.framework.version_label})"),
        *common_about(visible, made, report.partial),
        ("Numbers used", _numbers(report)),
    ]
    summary = Section(
        "Summary",
        [
            Column("Method"),
            Column("Headline", Kind.PERCENT),
            Column("What the headline is"),
            Column("Counted", Kind.TEXT),
            Column("Covered", Kind.INTEGER),
            Column("Partial", Kind.INTEGER),
            Column("Not covered", Kind.INTEGER),
            Column("Total", Kind.INTEGER),
        ],
        [],
        note=(
            f"{report.summary.leaves} items (framework items with nothing below them) in "
            f"{report.summary.groups} groups. {report.summary.links - report.summary.group_links} "
            f"accepted links counted; {report.summary.group_links} made to groups themselves, not "
            f"counted; {report.summary.bulk_links} accepted in bulk; "
            f"{report.summary.recheck_links} "
            f"need a re-check; {report.summary.waiting_links} suggestions waiting for review."
        ),
    )
    what = {
        Method.SINGLE: "share of items covered",
        Method.MULTIPLE: "share of items covered",
        Method.SUBORDINATE: "average over groups",
        Method.WEIGHTED: "degree of coverage (average over items)",
    }
    for method, figure in report.summary.methods.items():
        summary.rows.append(
            [
                METHOD_NAMES[method] + (" (this report)" if method is report.method else ""),
                figure.headline,
                what[method],
                figure.unit,
                figure.covered,
                figure.partial,
                figure.uncovered,
                figure.total,
            ]
        )
    columns = [Column("Group"), Column("All phases", Kind.PERCENT)]
    for column in report.columns:
        label = (
            column.label
            if column.kind == "phase"
            else "Programme outcomes"
            if column.kind == "programme"
            else "Modules without a phase"
        )
        columns.append(Column(label, Kind.PERCENT))
    heat = Section(
        "Heatmap",
        columns,
        [],
        note=(
            "Framework groups by phase: each cell is the average, over the items of the group, of "
            f"how covered each is by the links of that phase ({name})."
        ),
    )
    for group in report.tree.groups():
        cells = report.grid[group.id]
        heat.rows.append(
            [f"{group.code} {group.title}", cells["all"], *[cells[c.key] for c in report.columns]]
        )
    items = Section(
        "Items",
        [
            Column("Code"),
            Column("Item or group"),
            Column("Kind"),
            Column("Status"),
            Column("Figure", Kind.PERCENT),
            Column("Items below covered"),
            Column("Accepted links"),
            Column("Made to the group itself (not counted)", Kind.INTEGER),
            Column("Accepted in bulk", Kind.INTEGER),
            Column("Need a re-check", Kind.INTEGER),
            Column("Waiting for review", Kind.INTEGER),
            Column("Objectives", Kind.INTEGER),
        ],
        [],
        note="Every item and group in framework order.",
    )
    for r in report.rows:
        items.rows.append(
            [
                r.item.code,
                r.item.title,
                "Item" if r.is_leaf else "Group",
                STATUS_NAMES[r.status],
                r.value,
                None if r.is_leaf else f"{r.leaves_covered} of {r.leaves}",
                r.links if r.is_leaf else None,
                None if r.is_leaf else r.links,
                r.bulk_links,
                r.recheck_links,
                r.waiting,
                r.objectives,
            ]
        )
    return ReportDoc(
        key="coverage",
        title="Coverage report",
        about=about,
        method=name,
        made_on=report.generated_at,
        sections=[summary, heat, items],
    )


def gaps_doc(found: GapReport, visible: VisibleVersion) -> ReportDoc:
    report = found.report
    name = METHOD_NAMES[report.method]
    made = report.generated_at.strftime("%Y-%m-%d %H:%M UTC")
    about = [
        ("Report", "Gap report"),
        ("Method", f"{name}. {report.definition}"),
        ("Framework", f"{report.framework.name} ({report.framework.version_label})"),
        *common_about(visible, made, report.partial),
        ("Numbers used", _numbers(found)),
    ]
    gap_columns = [
        Column("Groups above"),
        Column("Code"),
        Column("Item or group"),
        Column("Status"),
        Column("Figure", Kind.PERCENT),
        Column("Why"),
        Column("Accepted links", Kind.INTEGER),
        Column("Waiting for review", Kind.INTEGER),
    ]

    def gap_row(g: coverage_report.Gap) -> list[object]:
        return [
            " > ".join(f"{p.code} {p.title}" for p in g.path),
            g.result.item.code,
            g.result.item.title,
            STATUS_NAMES[g.result.status],
            g.result.value,
            g.reason,
            g.result.links,
            g.result.waiting,
        ]

    sections = [
        Section(
            "Items not covered",
            gap_columns,
            [gap_row(g) for g in found.gaps],  # type: ignore[misc]
            note="Items with nothing below them that the method does not call covered "
            "(weighted coverage: under the low line); those with no accepted link first.",
        )
    ]
    if report.method is Method.SUBORDINATE:
        sections.append(
            Section(
                f"Groups under {report.policy.subordinate_min_percent}%",
                gap_columns,
                [gap_row(g) for g in found.group_gaps],  # type: ignore[misc]
                note="Groups where fewer of the items below them are covered by a single match.",
            )
        )
    objective_columns = [
        Column("Kind"),
        Column("Module"),
        Column("Session"),
        Column("Objective"),
        Column("Suggestions waiting", Kind.INTEGER),
    ]

    def objective_rows(rows: list[coverage_report.UnmappedObjective]) -> list[list[object]]:
        return [
            [
                LEVEL_NAMES.get(o.level.value, o.level.value),
                o.module_code,
                o.event_title,
                o.text,
                o.waiting,
            ]
            for o in rows
        ]

    sections.append(
        Section(
            f"Objectives with no mapping ({found.unlinked_total})",
            objective_columns,
            objective_rows(found.unlinked),  # type: ignore[arg-type]
            note="Objectives with no accepted link to this framework and nothing waiting."
            + (
                f" Showing {len(found.unlinked)} of {found.unlinked_total}."
                if found.unlinked_total > len(found.unlinked)
                else ""
            ),
        )
    )
    sections.append(
        Section(
            f"Objectives with suggestions waiting ({found.only_waiting_total})",
            objective_columns,
            objective_rows(found.only_waiting),  # type: ignore[arg-type]
            note="No accepted link yet, but suggestions or reviews wait: the quickest to close."
            + (
                f" Showing {len(found.only_waiting)} of {found.only_waiting_total}."
                if found.only_waiting_total > len(found.only_waiting)
                else ""
            ),
        )
    )
    return ReportDoc(
        key="gaps",
        title="Gap report",
        about=about,
        method=name,
        made_on=report.generated_at,
        sections=sections,
    )


async def build_coverage(ctx: ReportContext) -> ReportDoc:
    framework = await ctx.framework()
    report = await coverage_report.build_report(
        ctx.db, ctx.visible, framework, ctx.method, ctx.policy
    )
    return coverage_doc(report, ctx.visible)


async def build_gaps(ctx: ReportContext) -> ReportDoc:
    framework = await ctx.framework()
    found = await coverage_report.build_gaps(ctx.db, ctx.visible, framework, ctx.method, ctx.policy)
    return gaps_doc(found, ctx.visible)


REPORTS: dict[str, Builder] = {
    "coverage": build_coverage,
    "gaps": build_gaps,
}
