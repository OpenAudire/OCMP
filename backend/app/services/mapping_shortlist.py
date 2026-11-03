"""Choosing which framework items an AI run looks at for one objective (ADR 045).

The model is only asked about a short list, so the list decides what can be found. Each
candidate gets a hybrid score from three signals:

* **meaning**: cosine similarity of the objective and the item (embeddings);
* **words**: PostgreSQL full-text rank;
* **precedent**: the item was accepted for another objective that reads almost the same.

Items cross-referenced from the best few are added with a share of their score, and items the
objective is already linked to (in any state, rejected included) are left out. While
embeddings are off or unreachable the list is made from words alone and says why.
"""

import uuid
from dataclasses import dataclass
from typing import Literal

from redis.asyncio import Redis
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import MODEL_KEY, EmbeddingProvider
from app.core.config import Settings
from app.models import FrameworkItem, MappingLink, Objective
from app.models.framework import FrameworkCrossRef
from app.models.mapping import MappingStatus
from app.services.mapping_live import live_link
from app.services.retrieval import Mode, Notice, keyword_hits, similar_framework_items

DEFAULT_K = 10
POOL = 40
# The model gives unrelated text of one subject cosines in the high 0.7s and 0.8s (ADR 044), so
# a cosine only starts to count above this and is full at the top of the scale.
MEANING_FLOOR = 0.75
MEANING_SPAN = 0.20
# Precedent counts when the other objective is at least this similar (cosine).
PRECEDENT_FLOOR = 0.85
PRECEDENT_SPAN = 0.15
WEIGHTS_WITH_MEANING = (0.55, 0.30, 0.15)  # meaning, words, precedent
WEIGHTS_WORDS_ONLY = (0.0, 0.80, 0.20)
CROSS_REF_SHARE = 0.5
CROSS_REF_FROM_TOP = 3

_PRECEDENT_SQL = text(
    """
    WITH me AS (
        SELECT vector FROM embeddings
        WHERE entity_type = 'objective' AND entity_id = :objective_id AND model_key = :key
    )
    SELECT l.framework_item_id, max(1 - (e.vector <=> me.vector)) AS similarity
    FROM mapping_links l
    JOIN objectives o ON o.id = l.objective_id AND o.deleted_at IS NULL
    JOIN framework_items i ON i.id = l.framework_item_id
    JOIN embeddings e
      ON e.entity_id = o.id AND e.entity_type = 'objective' AND e.model_key = :key,
    me
    WHERE l.status = 'accepted' AND l.deleted_at IS NULL
      AND i.framework_id = :framework_id AND o.id <> :objective_id
      AND 1 - (e.vector <=> me.vector) >= :floor
    GROUP BY l.framework_item_id
    ORDER BY similarity DESC
    LIMIT :pool
    """
)


@dataclass(frozen=True)
class Candidate:
    item: FrameworkItem
    score: float
    # Which signals contributed, for the run record: "meaning", "words", "precedent", "reference".
    signals: tuple[str, ...]


@dataclass(frozen=True)
class Shortlist:
    candidates: list[Candidate]
    # Meaning when the vectors were used; keyword when the list is made from words alone.
    mode: Literal["meaning", "keyword"]
    notice: Notice | None = None


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


async def _precedent(
    db: AsyncSession, objective_id: uuid.UUID, framework_id: uuid.UUID
) -> dict[uuid.UUID, float]:
    rows = await db.execute(
        _PRECEDENT_SQL,
        {
            "objective_id": objective_id,
            "framework_id": framework_id,
            "key": MODEL_KEY,
            "floor": PRECEDENT_FLOOR,
            "pool": POOL,
        },
    )
    return {
        item_id: _clamp((float(sim) - PRECEDENT_FLOOR) / PRECEDENT_SPAN) for item_id, sim in rows
    }


async def shortlist(
    db: AsyncSession,
    settings: Settings,
    objective: Objective,
    framework_id: uuid.UUID,
    *,
    k: int = DEFAULT_K,
    provider: EmbeddingProvider | None = None,
    redis: Redis | None = None,
) -> Shortlist:
    """The ``k`` framework items most worth asking the model about for this objective."""
    retrieved = await similar_framework_items(
        db,
        settings,
        objective.text,
        framework_ids=[framework_id],
        limit=POOL,
        provider=provider,
        redis=redis,
    )
    meaning = retrieved.mode is Mode.MEANING
    words = (
        {h.item_id: h.score for h in retrieved.hits}
        if not meaning
        else {
            h.item_id: h.score for h in await keyword_hits(db, objective.text, [framework_id], POOL)
        }
    )
    meaning_scores = (
        {h.item_id: _clamp((h.score - MEANING_FLOOR) / MEANING_SPAN) for h in retrieved.hits}
        if meaning
        else {}
    )
    precedent = await _precedent(db, objective.id, framework_id) if meaning else {}

    w_meaning, w_words, w_precedent = WEIGHTS_WITH_MEANING if meaning else WEIGHTS_WORDS_ONLY
    scores: dict[uuid.UUID, float] = {}
    signals: dict[uuid.UUID, list[str]] = {}
    for item_id in set(meaning_scores) | set(words) | set(precedent):
        m, k_, p = (
            meaning_scores.get(item_id, 0.0),
            words.get(item_id, 0.0),
            precedent.get(item_id, 0.0),
        )
        scores[item_id] = w_meaning * m + w_words * k_ + w_precedent * p
        signals[item_id] = [
            name for name, value in (("meaning", m), ("words", k_), ("precedent", p)) if value > 0
        ]

    # Items the objective is already linked to are not asked about again, rejected ones included
    # (a rejection is a person's "no"), unless the wording changed after the rejection.
    linked: set[uuid.UUID] = set()
    for item_id, status, first_at, second_at in await db.execute(
        select(
            MappingLink.framework_item_id,
            MappingLink.status,
            MappingLink.first_reviewed_at,
            MappingLink.second_reviewed_at,
        ).where(MappingLink.objective_id == objective.id, live_link())
    ):
        decided = second_at or first_at
        changed = objective.text_changed_at
        if (
            status == MappingStatus.REJECTED
            and changed is not None
            and decided is not None
            and decided < changed
        ):
            continue
        linked.add(item_id)
    ranked = sorted(
        (i for i in scores if i not in linked and scores[i] > 0), key=lambda i: -scores[i]
    )

    # Cross-references of the best few come along with a share of their score.
    top = ranked[:CROSS_REF_FROM_TOP]
    if top:
        refs = await db.execute(
            select(FrameworkCrossRef.from_item_id, FrameworkCrossRef.to_item_id).where(
                or_(FrameworkCrossRef.from_item_id.in_(top), FrameworkCrossRef.to_item_id.in_(top))
            )
        )
        for from_id, to_id in refs:
            source, other = (from_id, to_id) if from_id in top else (to_id, from_id)
            if other in linked or other in scores:
                continue
            scores[other] = CROSS_REF_SHARE * scores[source]
            signals[other] = ["reference"]
            ranked.append(other)
        ranked.sort(key=lambda i: -scores[i])

    chosen = ranked[: max(1, k)]
    if not chosen:
        return Shortlist([], "meaning" if meaning else "keyword", retrieved.notice)
    items = {
        item.id: item
        for item in await db.scalars(
            select(FrameworkItem).where(
                FrameworkItem.id.in_(chosen), FrameworkItem.framework_id == framework_id
            )
        )
    }
    return Shortlist(
        [Candidate(items[i], scores[i], tuple(signals[i])) for i in chosen if i in items],
        "meaning" if meaning else "keyword",
        retrieved.notice,
    )
