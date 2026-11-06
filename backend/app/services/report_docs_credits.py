"""The credits and notional hours check as a report document (Slice 1.31, ADR 051, 035).

The check itself is ``credit_check`` (advice, never a block); this only lays its figures out so
the Excel and PDF exports and the report screen can show them like every other report. It needs
the whole version: the year and level totals would reveal modules a narrower role does not see.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.services import credit_check
from app.services.authorization import InvalidRequestError
from app.services.credit_check import Finding, HoursStatus, YearStatus
from app.services.report_context import ReportContext, common_about
from app.services.report_export import Column, Kind, ReportDoc, Section

HOURS_STATUS = {
    HoursStatus.OK: "Fits the credits",
    HoursStatus.UNDER: "Under the credits",
    HoursStatus.OVER: "Over the credits",
    HoursStatus.NO_CREDITS: "No credits set",
}
YEAR_STATUS = {
    YearStatus.OK: "Matches",
    YearStatus.UNDER: "Under",
    YearStatus.OVER: "Over",
    YearStatus.NOT_CHECKED: "Not checked",
}


def finding_text(finding: Finding) -> str:
    p = finding.params
    if finding.code == "total_differs_from_programme":
        return (
            f"The modules add up to {p['total']} credits, but the programme's total is "
            f"{p['programme']}."
        )
    if finding.code == "total_below_qualification_minimum":
        return (
            f"The modules add up to {p['total']} credits, below the qualification type's "
            f"minimum of {p['minimum']}."
        )
    if finding.code == "above_exit_level":
        return f"Modules above the programme's exit level (NQF {p['level']}): {p['modules']}."
    if finding.code == "exit_level_credits_low":
        return (
            f"Only {p['credits']} credits are at the exit level (NQF {p['level']}); at least "
            f"{p['minimum']} are wanted."
        )
    return finding.code


def _number(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


async def build_credits(ctx: ReportContext) -> ReportDoc:
    if not ctx.visible.view.full:
        raise InvalidRequestError(
            "The credits report needs the whole curriculum version; ask for report access to the "
            "programme."
        )
    made = datetime.now(UTC)
    check = await credit_check.version_credit_check(
        ctx.db, ctx.visible.version, ctx.visible.programme
    )
    policy = check.policy
    method = (
        "Notional hours are contact time, self-study time and assessment time. One credit "
        f"stands for {policy.hours_per_credit} hours; a module fits when its planned hours are "
        f"within {policy.tolerance_percent}% of credits times that. A year (a phase of kind "
        f"year) is compared with {policy.credits_per_year} credits exactly. These checks are "
        "advice and never block saving; verify the NQF figures against CHE/HEQSF."
    )
    modules = Section(
        "Modules",
        [
            Column("Code"),
            Column("Module"),
            Column("Credits", Kind.NUMBER),
            Column("NQF level", Kind.INTEGER),
            Column("Contact hours", Kind.NUMBER),
            Column("Self-study hours", Kind.NUMBER),
            Column("Assessment hours", Kind.NUMBER),
            Column("Planned hours", Kind.NUMBER),
            Column("Expected hours", Kind.NUMBER),
            Column("Difference", Kind.PERCENT),
            Column("Result"),
        ],
        [
            [
                m.code,
                m.name,
                _number(m.credits),
                m.nqf_level,
                _number(m.contact_hours),
                _number(m.self_study_hours),
                _number(m.assessment_hours),
                _number(m.planned_hours),
                _number(m.expected_hours),
                float(m.difference_percent) / 100 if m.difference_percent is not None else None,
                HOURS_STATUS[m.status],
            ]
            for m in check.modules
        ],
        note="Difference is planned hours against expected hours.",
    )
    years = Section(
        "Credits by phase",
        [
            Column("Phase"),
            Column("Kind"),
            Column("Modules", Kind.INTEGER),
            Column("Credits", Kind.NUMBER),
            Column("Expected credits", Kind.INTEGER),
            Column("Result"),
        ],
        [
            [
                y.name,
                y.kind.value,
                y.modules,
                _number(y.credits),
                y.expected_credits,
                YEAR_STATUS[y.status],
            ]
            for y in check.years
        ],
        note=(
            f"Modules outside any phase: {check.unphased_modules}, "
            f"{check.unphased_credits.normalize():f} credits."
        ),
    )
    levels = Section(
        "Credits by NQF level",
        [
            Column("NQF level", Kind.INTEGER),
            Column("Modules", Kind.INTEGER),
            Column("Credits", Kind.NUMBER),
        ],
        [[row.level, row.modules, _number(row.credits)] for row in check.levels],
        note=f"Total credits: {check.total_credits.normalize():f}.",
    )
    findings = Section(
        "Findings",
        [Column("Finding")],
        [[finding_text(f)] for f in check.findings] or [["No findings."]],
    )
    return ReportDoc(
        key="credits",
        title="Credits and notional hours",
        about=[
            ("Report", "Credits and notional hours"),
            ("Method", method),
            *common_about(ctx.visible, made.strftime("%Y-%m-%d %H:%M UTC"), False),
        ],
        method=method,
        made_on=made,
        sections=[modules, years, levels, findings],
    )
