"""Credits and notional hours checks: advice only, never blocks saving (ADR 035).

Rules (brief, section 9), with the figures from the institution's ``credits`` settings
(``CreditPolicy``):

- A module's planned hours are the contact time and the estimated self-study of its
  sessions plus the learner time of its assessments. They are compared with the declared
  credits x hours per credit; a difference beyond the tolerance is flagged "under" or
  "over". A module without credits is "no credits"; with 0 credits any planned time is
  "over".
- Each phase of kind "year" is compared with the typical credits per year (exact);
  other kinds of phase and the modules outside any phase are only totalled.
- Credits are totalled per NQF level, and checked against the programme: the total
  against the programme's total credits and the qualification type's minimum, modules
  above the programme's NQF exit level, and (when set) the credits at the exit level.

The rules are pure functions; the database functions only gather the figures.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CurriculumVersion, LearningEvent, Module, Phase, Programme, QualificationType
from app.models.curriculum import PhaseKind
from app.services.assessments import assessment_minutes
from app.services.institution_settings import get_institution, parse_settings
from app.services.policies import CreditPolicy


class HoursStatus(StrEnum):
    OK = "ok"
    UNDER = "under"
    OVER = "over"
    NO_CREDITS = "no_credits"


class YearStatus(StrEnum):
    OK = "ok"
    UNDER = "under"
    OVER = "over"
    NOT_CHECKED = "not_checked"


@dataclass(frozen=True)
class ModuleHours:
    """The planned hours of one module and how they compare with its credits."""

    module_id: uuid.UUID
    code: str
    name: str
    phase_id: uuid.UUID | None
    credits: Decimal | None
    nqf_level: int | None
    contact_hours: Decimal
    self_study_hours: Decimal
    assessment_hours: Decimal
    planned_hours: Decimal
    # Credits x hours per credit; None without credits.
    expected_hours: Decimal | None
    # Planned against expected, in percent of expected; None when it cannot be told.
    difference_percent: Decimal | None
    status: HoursStatus


def _hours(minutes: int) -> Decimal:
    return (Decimal(minutes) / 60).quantize(Decimal("0.1"))


def module_hours(
    module: Module,
    *,
    contact_minutes: int,
    self_study_minutes: int,
    assessment_minutes: int,
    policy: CreditPolicy,
) -> ModuleHours:
    """Compare a module's planned hours with its credits."""
    planned_minutes = contact_minutes + self_study_minutes + assessment_minutes
    planned = Decimal(planned_minutes) / 60
    expected: Decimal | None = None
    difference: Decimal | None = None
    if module.credits is None:
        status = HoursStatus.NO_CREDITS
    else:
        expected = module.credits * policy.hours_per_credit
        if expected > 0:
            difference = (planned - expected) / expected * 100
            if abs(difference) <= policy.tolerance_percent:
                status = HoursStatus.OK
            else:
                status = HoursStatus.UNDER if difference < 0 else HoursStatus.OVER
        else:
            status = HoursStatus.OK if planned == 0 else HoursStatus.OVER
    return ModuleHours(
        module_id=module.id,
        code=module.code,
        name=module.name,
        phase_id=module.phase_id,
        credits=module.credits,
        nqf_level=module.nqf_level,
        contact_hours=_hours(contact_minutes),
        self_study_hours=_hours(self_study_minutes),
        assessment_hours=_hours(assessment_minutes),
        planned_hours=planned.quantize(Decimal("0.1")),
        expected_hours=expected,
        difference_percent=difference.quantize(Decimal("0.1")) if difference is not None else None,
        status=status,
    )


@dataclass(frozen=True)
class YearCredits:
    """The credits of one phase; "year" phases are compared with the typical credits."""

    phase_id: uuid.UUID
    name: str
    kind: PhaseKind
    credits: Decimal
    modules: int
    modules_without_credits: int
    expected_credits: int | None
    status: YearStatus


@dataclass(frozen=True)
class LevelCredits:
    """The credits of the modules at one NQF level (None: modules without a level)."""

    level: int | None
    credits: Decimal
    modules: int


@dataclass(frozen=True)
class Finding:
    """A programme-level observation; the UI words it from ``code`` and ``params``."""

    code: str
    params: dict[str, str | int] = field(default_factory=dict)


@dataclass(frozen=True)
class VersionCreditCheck:
    policy: CreditPolicy
    modules: list[ModuleHours]
    years: list[YearCredits]
    # Modules outside any phase (longitudinal modules): totalled, not compared.
    unphased_credits: Decimal
    unphased_modules: int
    levels: list[LevelCredits]
    total_credits: Decimal
    programme_total_credits: int | None
    qualification_name: str | None
    qualification_min_credits: int | None
    exit_level: int | None
    # Credits wanted at the exit level (institution setting, else the qualification type).
    exit_level_minimum: int | None
    findings: list[Finding]


async def credit_policy(db: AsyncSession) -> CreditPolicy:
    """The credit policy of this instance's institution (defaults if none is set up)."""
    institution = await get_institution(db)
    if institution is None:
        return CreditPolicy()
    return parse_settings(institution.settings).credits


async def _session_minutes(
    db: AsyncSession, module_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, tuple[int, int]]:
    if not module_ids:
        return {}
    rows = await db.execute(
        select(
            LearningEvent.module_id,
            func.coalesce(func.sum(LearningEvent.contact_minutes), 0),
            func.coalesce(func.sum(LearningEvent.self_study_minutes), 0),
        )
        .where(LearningEvent.module_id.in_(module_ids), LearningEvent.deleted_at.is_(None))
        .group_by(LearningEvent.module_id)
    )
    return {module_id: (int(c), int(s)) for module_id, c, s in rows}


async def modules_hours(
    db: AsyncSession, modules: Sequence[Module], policy: CreditPolicy
) -> list[ModuleHours]:
    """The hours check of each module, in the order given."""
    ids = [m.id for m in modules]
    sessions = await _session_minutes(db, ids)
    assessments = await assessment_minutes(db, ids)
    return [
        module_hours(
            module,
            contact_minutes=sessions.get(module.id, (0, 0))[0],
            self_study_minutes=sessions.get(module.id, (0, 0))[1],
            assessment_minutes=assessments.get(module.id, 0),
            policy=policy,
        )
        for module in modules
    ]


def _year_status(credits: Decimal, expected: int) -> YearStatus:
    if credits == expected:
        return YearStatus.OK
    return YearStatus.UNDER if credits < expected else YearStatus.OVER


def exit_level_minimum(
    policy: CreditPolicy, qualification: QualificationType | None, exit_level: int | None
) -> int | None:
    """Credits wanted at the exit level: the institution's own figure when it sets one,
    else the qualification type's (which applies at the type's own exit level)."""
    if policy.min_exit_level_credits is not None:
        return policy.min_exit_level_credits
    if (
        qualification is not None
        and qualification.min_exit_level_credits is not None
        and qualification.nqf_exit_level == exit_level
    ):
        return qualification.min_exit_level_credits
    return None


def check_credits(
    *,
    policy: CreditPolicy,
    phases: Sequence[Phase],
    hours: Sequence[ModuleHours],
    programme_total_credits: int | None,
    qualification: QualificationType | None,
    exit_level: int | None,
) -> VersionCreditCheck:
    """Totals per year and NQF level, and the programme-level findings (pure)."""
    live_phases = {p.id: p for p in phases}
    years: list[YearCredits] = []
    for phase in phases:
        members = [h for h in hours if h.phase_id == phase.id]
        credits = sum((h.credits or Decimal(0) for h in members), Decimal(0))
        expected = policy.credits_per_year if phase.kind == PhaseKind.YEAR else None
        years.append(
            YearCredits(
                phase_id=phase.id,
                name=phase.name,
                kind=phase.kind,
                credits=credits,
                modules=len(members),
                modules_without_credits=sum(1 for h in members if h.credits is None),
                expected_credits=expected,
                status=(
                    _year_status(credits, expected)
                    if expected is not None
                    else YearStatus.NOT_CHECKED
                ),
            )
        )
    # Modules whose phase was deleted are shown across phases, like longitudinal ones.
    unphased = [h for h in hours if h.phase_id not in live_phases]
    levels: dict[int | None, list[ModuleHours]] = {}
    for h in hours:
        levels.setdefault(h.nqf_level, []).append(h)
    level_rows = [
        LevelCredits(
            level=level,
            credits=sum((h.credits or Decimal(0) for h in members), Decimal(0)),
            modules=len(members),
        )
        for level, members in sorted(levels.items(), key=lambda kv: (kv[0] is None, kv[0] or 0))
    ]
    total = sum((h.credits or Decimal(0) for h in hours), Decimal(0))

    findings: list[Finding] = []
    if programme_total_credits is not None and total != programme_total_credits:
        findings.append(
            Finding(
                "total_differs_from_programme",
                {"total": format(total.normalize(), "f"), "programme": programme_total_credits},
            )
        )
    minimum = qualification.min_total_credits if qualification else None
    if minimum is not None and total < minimum:
        findings.append(
            Finding(
                "total_below_qualification_minimum",
                {"total": format(total.normalize(), "f"), "minimum": minimum},
            )
        )
    if exit_level is not None:
        above = [h.code for h in hours if h.nqf_level is not None and h.nqf_level > exit_level]
        if above:
            findings.append(
                Finding("above_exit_level", {"level": exit_level, "modules": ", ".join(above)})
            )
        wanted = exit_level_minimum(policy, qualification, exit_level)
        if wanted is not None:
            at_exit = next(
                (row.credits for row in level_rows if row.level == exit_level), Decimal(0)
            )
            if at_exit < wanted:
                findings.append(
                    Finding(
                        "exit_level_credits_low",
                        {
                            "level": exit_level,
                            "credits": format(at_exit.normalize(), "f"),
                            "minimum": wanted,
                        },
                    )
                )
    return VersionCreditCheck(
        policy=policy,
        modules=list(hours),
        years=years,
        unphased_credits=sum((h.credits or Decimal(0) for h in unphased), Decimal(0)),
        unphased_modules=len(unphased),
        levels=level_rows,
        total_credits=total,
        programme_total_credits=programme_total_credits,
        qualification_name=qualification.name if qualification else None,
        qualification_min_credits=minimum,
        exit_level=exit_level,
        exit_level_minimum=exit_level_minimum(policy, qualification, exit_level),
        findings=findings,
    )


async def version_credit_check(
    db: AsyncSession, version: CurriculumVersion, programme: Programme
) -> VersionCreditCheck:
    """The credits and hours check of every live module of a version."""
    policy = await credit_policy(db)
    phases = list(
        await db.scalars(
            select(Phase)
            .where(Phase.version_id == version.id, Phase.deleted_at.is_(None))
            .order_by(Phase.position, Phase.name)
        )
    )
    modules = list(
        await db.scalars(
            select(Module)
            .where(Module.version_id == version.id, Module.deleted_at.is_(None))
            .order_by(Module.position, Module.code)
        )
    )
    qualification = (
        await db.get(QualificationType, programme.qualification_type_id)
        if programme.qualification_type_id
        else None
    )
    exit_level = programme.nqf_exit_level
    if exit_level is None and qualification is not None:
        exit_level = qualification.nqf_exit_level
    return check_credits(
        policy=policy,
        phases=phases,
        hours=await modules_hours(db, modules, policy),
        programme_total_credits=programme.total_credits,
        qualification=qualification,
        exit_level=exit_level,
    )
