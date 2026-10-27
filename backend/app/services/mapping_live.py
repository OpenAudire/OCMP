"""Which mapping links count: the one filter every mapping read uses (ADR 043).

A link counts only if it is not soft-deleted and its objective is not soft-deleted.
Links are soft-deleted together with their objective, with the objective's own
``deleted_at``, so restoring the objective restores exactly those links. Anything that
reads ``MappingLink`` (counts, queues, workspaces, reports, exports, copy forward) puts
``live_link()`` in its ``where`` clause; do not rewrite the rule inline.
"""

import uuid
from collections.abc import Collection
from datetime import datetime

from sqlalchemy import ColumnElement, and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MappingLink, Objective


def live_link() -> ColumnElement[bool]:
    """Condition: the link is not deleted and neither is its objective."""
    return and_(
        MappingLink.deleted_at.is_(None),
        MappingLink.objective_id.in_(select(Objective.id).where(Objective.deleted_at.is_(None))),
    )


async def soft_delete_links(
    db: AsyncSession, objective_ids: Collection[uuid.UUID], *, at: datetime
) -> int:
    """Soft-delete the live links of these objectives with the objectives' ``deleted_at``.

    Call it inside the same ``audit_operation`` as the objectives' own deletion. Changes the
    rows through the ORM so each is audited. Returns how many links were deleted.
    """
    if not objective_ids:
        return 0
    links = list(
        await db.scalars(
            select(MappingLink).where(
                MappingLink.objective_id.in_(list(objective_ids)), MappingLink.deleted_at.is_(None)
            )
        )
    )
    for link in links:
        link.deleted_at = at
    await db.flush()
    return len(links)


async def restore_links(db: AsyncSession, objective: Objective) -> int:
    """Restore the links that were deleted together with this (still deleted) objective.

    Only links whose ``deleted_at`` equals the objective's are restored: a link deleted at
    another time is left deleted. A link whose pair is live again (a newer link for the
    same item) stays deleted, so the one-live-link-per-pair rule cannot be broken. Call it
    before clearing the objective's own ``deleted_at``. Returns how many were restored.
    """
    at = objective.deleted_at
    if at is None:
        return 0
    links = list(
        await db.scalars(
            select(MappingLink).where(
                MappingLink.objective_id == objective.id, MappingLink.deleted_at == at
            )
        )
    )
    live_items = set(
        await db.scalars(
            select(MappingLink.framework_item_id).where(
                MappingLink.objective_id == objective.id, MappingLink.deleted_at.is_(None)
            )
        )
    )
    restored = 0
    for link in links:
        if link.framework_item_id in live_items:
            continue
        link.restore()
        restored += 1
    await db.flush()
    return restored


async def orphan_links(db: AsyncSession) -> list[tuple[MappingLink, datetime]]:
    """Live links whose objective is deleted, each with the objective's ``deleted_at``."""
    rows = await db.execute(
        select(MappingLink, Objective.deleted_at)
        .join(Objective, Objective.id == MappingLink.objective_id)
        .where(MappingLink.deleted_at.is_(None), Objective.deleted_at.is_not(None))
        .order_by(MappingLink.created_at)
    )
    return [(link, at) for link, at in rows if at is not None]


async def clean_orphan_links(db: AsyncSession, *, apply: bool) -> int:
    """Soft-delete live links of deleted objectives (data hygiene for installs from before
    ADR 043). Dry run unless ``apply``; returns how many links there are or were deleted.

    Each link takes its objective's ``deleted_at``, as if it had been deleted with it, so
    restoring the objective would bring them back. Callers wrap it in ``audit_operation``.
    """
    orphans = await orphan_links(db)
    if apply:
        for link, at in orphans:
            link.deleted_at = at
        await db.flush()
    return len(orphans)
