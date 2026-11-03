"""Making and caching embeddings of objectives and framework items (ADR 044).

An item is embedded again only when the hash of its prepared text changes. Texts that the
privacy guard's detectors flag are embedded anyway: the server is local and the text is
already stored. They are counted (never logged) and the bulk quality check lists them so the
wording gets fixed.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import privacy
from app.ai.embeddings import MODEL_KEY, EmbeddingProvider, text_hash
from app.core.logging import get_logger
from app.models import Framework, FrameworkItem, Objective
from app.models.curriculum import ObjectiveStatus
from app.models.embedding import EmbeddedType, Embedding
from app.models.framework import FrameworkStatus
from app.services.objective_duplicates import refresh_similarities

logger = get_logger(__name__)

# Items sent to the server per call; the provider splits these into its own batches.
CHUNK = 128


@dataclass(frozen=True)
class SyncResult:
    embedded: int = 0
    unchanged: int = 0
    removed: int = 0
    # Texts embedded although the detectors found something in them (counts only).
    flagged: int = 0
    # The items whose vector was made or replaced (their near-duplicate pairs are stale).
    changed_ids: tuple[uuid.UUID, ...] = ()


def framework_item_text(title: str, description: str) -> str:
    """What is embedded for a framework item: its title, then its description."""
    description = description.strip()
    return f"{title.strip()}. {description}" if description else title.strip()


async def _live_texts(
    db: AsyncSession, entity_type: EmbeddedType, ids: Sequence[uuid.UUID] | None
) -> dict[uuid.UUID, str]:
    """The texts of the live items of a type (only ``ids`` when given)."""
    if entity_type is EmbeddedType.OBJECTIVE:
        query = select(Objective.id, Objective.text).where(
            Objective.deleted_at.is_(None), Objective.status != ObjectiveStatus.RETIRED
        )
        if ids is not None:
            query = query.where(Objective.id.in_(ids))
        return {row.id: row.text for row in await db.execute(query)}
    items = (
        select(FrameworkItem.id, FrameworkItem.title, FrameworkItem.description)
        .join(Framework, Framework.id == FrameworkItem.framework_id)
        .where(Framework.deleted_at.is_(None), Framework.status != FrameworkStatus.DRAFT)
    )
    if ids is not None:
        items = items.where(FrameworkItem.id.in_(ids))
    return {
        row.id: framework_item_text(row.title, row.description) for row in await db.execute(items)
    }


async def sync_embeddings(
    db: AsyncSession,
    provider: EmbeddingProvider,
    entity_type: EmbeddedType,
    *,
    ids: Sequence[uuid.UUID] | None = None,
) -> SyncResult:
    """Embed what is new or changed and, for a whole-type sync, drop what is gone.

    ``ids`` limits the work to those items (nothing is removed then, except the vectors of
    listed items that are no longer live). Without ``ids`` every live item is checked and
    vectors of deleted items and of older recipes are removed.

    Raises:
        ProviderError: If the embeddings server cannot be reached or answers badly. Vectors
            made before the failure in earlier chunks are kept (the caller commits).
    """
    texts = await _live_texts(db, entity_type, ids)
    stored_query = select(Embedding).where(
        Embedding.entity_type == entity_type, Embedding.model_key == MODEL_KEY
    )
    if ids is not None:
        stored_query = stored_query.where(Embedding.entity_id.in_(ids))
    stored = {row.entity_id: row for row in await db.scalars(stored_query)}

    removed = 0
    gone = [entity_id for entity_id in stored if entity_id not in texts]
    if gone:
        await db.execute(
            delete(Embedding).where(
                Embedding.entity_type == entity_type,
                Embedding.model_key == MODEL_KEY,
                Embedding.entity_id.in_(gone),
            )
        )
        removed += len(gone)
    if ids is None:
        stale = await db.execute(
            delete(Embedding).where(
                Embedding.entity_type == entity_type, Embedding.model_key != MODEL_KEY
            )
        )
        removed += stale.rowcount or 0  # type: ignore[attr-defined]

    wanted = [
        (entity_id, text, text_hash(text))
        for entity_id, text in texts.items()
        if entity_id not in stored or stored[entity_id].text_hash != text_hash(text)
    ]
    unchanged = len(texts) - len(wanted)
    known_names = await privacy.load_known_names(db)
    embedded = flagged = 0
    changed: list[uuid.UUID] = []
    for start in range(0, len(wanted), CHUNK):
        chunk = wanted[start : start + CHUNK]
        vectors = await provider.embed([text for _, text, _ in chunk])
        for (entity_id, text, digest), vector in zip(chunk, vectors, strict=True):
            if privacy.detect(text, known_names):
                flagged += 1
            row = stored.get(entity_id)
            if row is None:
                db.add(
                    Embedding(
                        entity_type=entity_type,
                        entity_id=entity_id,
                        model_key=MODEL_KEY,
                        text_hash=digest,
                        vector=vector,
                    )
                )
            else:
                row.text_hash = digest
                row.vector = vector
            embedded += 1
            changed.append(entity_id)
        await db.flush()
    result = SyncResult(embedded, unchanged, removed, flagged, tuple(changed))
    logger.info(
        "embeddings_synced",
        entity_type=entity_type.value,
        embedded=result.embedded,
        unchanged=result.unchanged,
        removed=result.removed,
        flagged=result.flagged,
    )
    return result


async def sweep(
    db: AsyncSession, provider: EmbeddingProvider, entity_type: EmbeddedType
) -> SyncResult:
    """Embed everything of a type that is new or changed; for objectives also refresh the
    near-duplicate pairs of each one that changed."""
    result = await sync_embeddings(db, provider, entity_type)
    if entity_type is EmbeddedType.OBJECTIVE:
        for objective_id in result.changed_ids:
            await refresh_similarities(db, objective_id)
    return result


@dataclass(frozen=True)
class Coverage:
    entity_type: EmbeddedType
    live: int
    embedded: int


async def coverage(db: AsyncSession) -> list[Coverage]:
    """How many live items of each type have a vector made with the current recipe."""
    found: list[Coverage] = []
    for kind in EmbeddedType:
        live = await _live_texts(db, kind, None)
        embedded = await db.scalar(
            select(func.count())
            .select_from(Embedding)
            .where(
                Embedding.entity_type == kind,
                Embedding.model_key == MODEL_KEY,
                Embedding.entity_id.in_(list(live)),
            )
        )
        found.append(Coverage(kind, len(live), embedded or 0))
    return found
