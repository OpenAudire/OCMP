"""The key figures of a curriculum version and their daily snapshots (Slice 1.28, ADR 058).

``compute_metrics`` works out the figures the committee dashboard shows (how much of the curriculum
is mapped, how well each framework in use is covered, how many modules are outside the credit
tolerance) for **what a person is allowed to see** (ADR 027). ``take_snapshot`` stores the same
figures for the **whole** version once a day, so the dashboard can draw trends. A snapshot holds
counts and shares only.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import (
    CurriculumVersion,
    Framework,
    FrameworkItem,
    MappingLink,
    MetricSnapshot,
    Objective,
    Programme,
)
from app.models.curriculum import VersionStatus
from app.models.framework import FrameworkStatus
from app.models.mapping import MappingStatus
from app.services import coverage_report, credit_check
from app.services.coverage_engine import Method
from app.services.curriculum_read import CurriculumAccess, VersionView, VisibleVersion
from app.services.mapping_live import live_link
from app.services.policies import CoveragePolicy, coverage_policy_for_version
from app.services.search import visible_objective_ids

SERIES_DAYS = 56  # the "last 8 weeks" of the dashboard
MAX_FRAMEWORKS = 5


def full_view(version: CurriculumVersion, programme: Programme) -> VisibleVersion:
    """The whole version, for the system's own figures (snapshots): not a person's view."""
    return VisibleVersion(version, programme, VersionView(full=True), CurriculumAccess())


def today(timezone: str | None = None) -> date:
    """Today's date in the installation's time zone (``TIMEZONE``), not the server's."""
    zone = ZoneInfo(timezone or get_settings().timezone)
    return datetime.now(zone).date()


@dataclass(frozen=True)
class ObjectiveCounts:
    total: int
    mapped: int
    # Not mapped yet, but a suggestion or a review is waiting.
    waiting: int


async def objective_counts(db: AsyncSession, visible: VisibleVersion) -> ObjectiveCounts:
    """Objectives the person sees, those with an accepted link (coverage 1 or more) and those
    that only have a link waiting for a decision."""
    allowed = await visible_objective_ids(db, visible)
    total = await db.scalar(select(func.count()).select_from(allowed.subquery())) or 0
    accepted = (
        select(MappingLink.objective_id)
        .where(
            MappingLink.objective_id.in_(allowed),
            MappingLink.status == MappingStatus.ACCEPTED,
            MappingLink.coverage >= 1,
            live_link(),
        )
        .distinct()
    )
    mapped = await db.scalar(select(func.count()).select_from(accepted.subquery())) or 0
    waiting_query = (
        select(MappingLink.objective_id)
        .where(
            MappingLink.objective_id.in_(allowed),
            MappingLink.objective_id.not_in(accepted),
            MappingLink.status.in_([MappingStatus.SUGGESTED, MappingStatus.NEEDS_SECOND_REVIEW]),
            live_link(),
        )
        .distinct()
    )
    waiting = await db.scalar(select(func.count()).select_from(waiting_query.subquery())) or 0
    return ObjectiveCounts(total=total, mapped=mapped, waiting=waiting)


async def frameworks_in_use(
    db: AsyncSession, version_id: uuid.UUID, visible: VisibleVersion
) -> list[Framework]:
    """Frameworks (not drafts) that the objectives the person sees are linked to, most links
    first."""
    allowed = await visible_objective_ids(db, visible)
    rows = await db.execute(
        select(Framework, func.count(MappingLink.id))
        .join(FrameworkItem, FrameworkItem.framework_id == Framework.id)
        .join(MappingLink, MappingLink.framework_item_id == FrameworkItem.id)
        .join(Objective, Objective.id == MappingLink.objective_id)
        .where(
            Objective.id.in_(allowed),
            Objective.version_id == version_id,
            MappingLink.status != MappingStatus.REJECTED,
            Framework.status != FrameworkStatus.DRAFT,
            Framework.deleted_at.is_(None),
            live_link(),
        )
        .group_by(Framework.id)
        .order_by(func.count(MappingLink.id).desc(), Framework.name)
        .limit(MAX_FRAMEWORKS)
    )
    return [framework for framework, _count in rows]


async def compute_metrics(
    db: AsyncSession, visible: VisibleVersion, policy: CoveragePolicy | None = None
) -> dict[str, Any]:
    """The key figures for what ``visible`` shows. JSON-ready (they are what a snapshot stores)."""
    policy = policy or await coverage_policy_for_version(db, visible.version.id)
    counts = await objective_counts(db, visible)
    frameworks: dict[str, Any] = {}
    for framework in await frameworks_in_use(db, visible.version.id, visible):
        report = await coverage_report.build_report(db, visible, framework, Method.WEIGHTED, policy)
        weighted = report.summary.methods[Method.WEIGHTED]
        single = report.summary.methods[Method.SINGLE]
        frameworks[str(framework.id)] = {
            "name": framework.name,
            "weighted": weighted.headline,
            "single": single.headline,
            "uncovered": single.uncovered,
            "items": single.total,
        }
    check = await credit_check.version_credit_check(db, visible.version, visible.programme)
    shown = [m for m in check.modules if visible.view.shows_module(m.module_id)]
    credits = {
        "modules": len(shown),
        "issues": sum(
            1
            for m in shown
            if m.status in (credit_check.HoursStatus.UNDER, credit_check.HoursStatus.OVER)
        ),
        "no_credits": sum(1 for m in shown if m.status is credit_check.HoursStatus.NO_CREDITS),
    }
    return {
        "objectives": {"total": counts.total, "mapped": counts.mapped, "waiting": counts.waiting},
        "frameworks": frameworks,
        "credits": credits,
    }


async def take_snapshot(
    db: AsyncSession, version: CurriculumVersion, programme: Programme, on: date | None = None
) -> MetricSnapshot:
    """Store today's figures for the whole version; the same day again replaces them."""
    day = on or today()
    metrics = await compute_metrics(db, full_view(version, programme))
    snapshot = await db.scalar(
        select(MetricSnapshot).where(
            MetricSnapshot.version_id == version.id, MetricSnapshot.taken_on == day
        )
    )
    if snapshot is None:
        snapshot = MetricSnapshot(version_id=version.id, taken_on=day, metrics=metrics)
        db.add(snapshot)
    else:
        snapshot.metrics = metrics
    await db.flush()
    return snapshot


def _ramp(live: dict[str, Any], share: float, behind: int) -> dict[str, Any]:
    """Figures ``share`` (0 to 1) of the way to ``live``; ``behind`` steps before the end."""
    o = live["objectives"]
    frameworks = {}
    for key, f in live["frameworks"].items():
        covered = f["items"] - f["uncovered"]
        frameworks[key] = {
            **f,
            "weighted": None if f["weighted"] is None else round(f["weighted"] * share, 4),
            "single": None if f["single"] is None else round(f["single"] * share, 4),
            "uncovered": f["items"] - round(covered * share),
        }
    return {
        "objectives": {
            "total": o["total"],
            "mapped": round(o["mapped"] * share),
            "waiting": o["waiting"] + round((o["total"] - o["mapped"]) * (1 - share) * 0.3),
        },
        "frameworks": frameworks,
        "credits": {**live["credits"], "issues": live["credits"]["issues"] + behind // 3},
    }


async def seed_history(
    db: AsyncSession,
    version: CurriculumVersion,
    programme: Programme,
    weeks: int = 8,
    on: date | None = None,
) -> int:
    """A **fictional** weekly history for the demo data, rising towards today's real figures, so the
    dashboard shows trend lines on a fresh install. Days that already have a snapshot are kept.
    Returns how many were written. Never used on a real installation's data."""
    end = on or today()
    live = await compute_metrics(db, full_view(version, programme))
    written = 0
    for step in range(weeks):
        behind = weeks - 1 - step
        day = end - timedelta(days=7 * behind)
        exists = await db.scalar(
            select(MetricSnapshot.id).where(
                MetricSnapshot.version_id == version.id, MetricSnapshot.taken_on == day
            )
        )
        if exists:
            continue
        share = 0.4 + 0.6 * (step / (weeks - 1)) if weeks > 1 else 1.0
        db.add(
            MetricSnapshot(
                version_id=version.id,
                taken_on=day,
                metrics=live if behind == 0 else _ramp(live, share, behind),
            )
        )
        written += 1
    await db.flush()
    return written


async def take_all_snapshots(db: AsyncSession, on: date | None = None) -> int:
    """A snapshot of every draft and published version; returns how many were taken."""
    rows = (
        await db.execute(
            select(CurriculumVersion, Programme)
            .join(Programme, Programme.id == CurriculumVersion.programme_id)
            .where(
                CurriculumVersion.deleted_at.is_(None),
                Programme.deleted_at.is_(None),
                CurriculumVersion.status.in_([VersionStatus.DRAFT, VersionStatus.PUBLISHED]),
            )
        )
    ).all()
    for version, programme in rows:
        await take_snapshot(db, version, programme, on)
    return len(rows)


async def series(
    db: AsyncSession, version_id: uuid.UUID, on: date | None = None
) -> list[tuple[date, dict[str, Any]]]:
    """The snapshots of the last ``SERIES_DAYS`` days, oldest first."""
    since = (on or today()) - timedelta(days=SERIES_DAYS)
    rows = await db.execute(
        select(MetricSnapshot.taken_on, MetricSnapshot.metrics)
        .where(MetricSnapshot.version_id == version_id, MetricSnapshot.taken_on >= since)
        .order_by(MetricSnapshot.taken_on)
    )
    return [(taken_on, metrics) for taken_on, metrics in rows]
