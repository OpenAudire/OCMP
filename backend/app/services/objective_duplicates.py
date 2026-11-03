"""Near-duplicate objectives, found from stored embeddings (ADR 044).

A background job calls ``refresh_similarities`` after an objective is saved. It keeps the
close pairs of one objective in ``objective_similarities``. Readers apply the institution's
threshold, so changing it needs no recomputation, and show a pair only when the user may see
both objectives (ADR 027).
"""

import uuid
from collections.abc import Collection
from dataclasses import dataclass

from sqlalchemy import and_, delete, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import MODEL_KEY
from app.core.logging import get_logger
from app.models import Objective
from app.models.curriculum import ObjectiveStatus
from app.models.embedding import ObjectiveSimilarity
from app.services.policies import NEAR_DUPLICATE_FLOOR_PERCENT

logger = get_logger(__name__)

# The closest others kept per refreshed objective (a pair is kept if either side finds it).
NEIGHBOURS = 10

# Exact search inside one version and level. The scope is a materialised subquery so the
# vector index is not used: an index search that filters afterwards would be crowded out by
# the identical text copy forward puts in other versions.
_NEIGHBOURS_SQL = text(
    """
    WITH me AS (
        SELECT vector FROM embeddings
        WHERE entity_type = 'objective' AND entity_id = :me AND model_key = :key
    ),
    scope AS MATERIALIZED (
        SELECT o.id, e.vector
        FROM objectives o
        JOIN embeddings e
          ON e.entity_id = o.id AND e.entity_type = 'objective' AND e.model_key = :key
        WHERE o.version_id = :version_id AND o.level = :level
          AND o.deleted_at IS NULL AND o.status <> 'retired' AND o.id <> :me
    )
    SELECT scope.id, 1 - (scope.vector <=> me.vector) AS similarity
    FROM scope, me
    ORDER BY scope.vector <=> me.vector
    LIMIT :k
    """
)


@dataclass(frozen=True)
class SimilarPair:
    objective_id: uuid.UUID
    other_id: uuid.UUID
    similarity: float


def _ordered(first: uuid.UUID, second: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    return (first, second) if first < second else (second, first)


async def refresh_similarities(db: AsyncSession, objective_id: uuid.UUID) -> int:
    """Recompute the close pairs of one objective; returns how many were stored.

    The pairs it was in are removed first, so a changed or deleted objective never leaves a
    stale pair. Nothing is stored while the objective has no vector.
    """
    await db.execute(
        delete(ObjectiveSimilarity).where(
            or_(
                ObjectiveSimilarity.objective_id == objective_id,
                ObjectiveSimilarity.other_objective_id == objective_id,
            )
        )
    )
    objective = await db.scalar(
        select(Objective).where(Objective.id == objective_id, Objective.deleted_at.is_(None))
    )
    if objective is None or objective.status == ObjectiveStatus.RETIRED:
        return 0
    rows = (
        await db.execute(
            _NEIGHBOURS_SQL,
            {
                "me": objective.id,
                "key": MODEL_KEY,
                "version_id": objective.version_id,
                "level": objective.level.value,
                "k": NEIGHBOURS,
            },
        )
    ).all()
    stored = 0
    for other_id, similarity in rows:
        if similarity < NEAR_DUPLICATE_FLOOR_PERCENT / 100:
            continue
        first, second = _ordered(objective.id, other_id)
        db.add(
            ObjectiveSimilarity(
                objective_id=first,
                other_objective_id=second,
                model_key=MODEL_KEY,
                similarity=min(1.0, float(similarity)),
            )
        )
        stored += 1
    await db.flush()
    logger.debug("objective_similarities_refreshed", objective_id=str(objective.id), pairs=stored)
    return stored


async def pairs_among(
    db: AsyncSession, objective_ids: Collection[uuid.UUID], min_percent: int
) -> list[SimilarPair]:
    """Stored pairs at or above ``min_percent`` where both objectives are in ``objective_ids``."""
    if len(objective_ids) < 2:
        return []
    ids = list(objective_ids)
    rows = await db.execute(
        select(
            ObjectiveSimilarity.objective_id,
            ObjectiveSimilarity.other_objective_id,
            ObjectiveSimilarity.similarity,
        ).where(
            ObjectiveSimilarity.model_key == MODEL_KEY,
            ObjectiveSimilarity.similarity >= min_percent / 100,
            and_(
                ObjectiveSimilarity.objective_id.in_(ids),
                ObjectiveSimilarity.other_objective_id.in_(ids),
            ),
        )
    )
    return [SimilarPair(a, b, s) for a, b, s in rows.all()]
