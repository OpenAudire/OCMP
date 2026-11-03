"""Finding framework items that fit a text: by meaning when embeddings work, else by words.

The AI mapping shortlist (Slice 1.16) and search (Slice 1.20) go through here. When the
embeddings server is off, unreachable or has nothing for the chosen frameworks, the answer
comes from full-text search with a ``notice`` saying why. It is never an error (ADR 044).
"""

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

import httpx
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import (
    MODEL_KEY,
    EmbeddingProvider,
    LocalEmbeddingProvider,
    get_embedding_provider,
)
from app.ai.errors import ProviderError
from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_READY_KEY = "embeddings:ready"
_READY_SECONDS = 30


class EmbeddingsState(StrEnum):
    OFF = "off"
    READY = "ready"
    UNREACHABLE = "unreachable"


class Mode(StrEnum):
    MEANING = "meaning"
    KEYWORD = "keyword"


class Notice(StrEnum):
    """Why the answer came from words and not meaning (frontend key ``retrieval.notice.<code>``)."""

    EMBEDDINGS_OFF = "embeddings_off"
    EMBEDDINGS_UNREACHABLE = "embeddings_unreachable"
    NOT_EMBEDDED_YET = "not_embedded_yet"


@dataclass(frozen=True)
class Hit:
    item_id: uuid.UUID
    # 0 to 1. Meaning: cosine similarity. Keyword: the rank scaled against the best hit.
    score: float


@dataclass(frozen=True)
class Retrieved:
    hits: list[Hit]
    mode: Mode
    notice: Notice | None = None


async def embeddings_state(
    settings: Settings,
    redis: Redis | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> EmbeddingsState:
    """Off, ready, or unreachable. A health answer is remembered for 30 seconds."""
    if not settings.embeddings_local:
        return EmbeddingsState.OFF
    if redis is not None:
        cached = await redis.get(_READY_KEY)
        if cached is not None:
            return EmbeddingsState.READY if cached == "1" else EmbeddingsState.UNREACHABLE
    try:
        provider = LocalEmbeddingProvider(settings.embeddings_local_url, transport)
        ready = await provider.is_ready()
    except ProviderError:
        ready = False
    if redis is not None:
        await redis.set(_READY_KEY, "1" if ready else "0", ex=_READY_SECONDS)
    return EmbeddingsState.READY if ready else EmbeddingsState.UNREACHABLE


_MEANING_SQL = text(
    """
    WITH scope AS MATERIALIZED (
        SELECT e.entity_id, e.vector
        FROM embeddings e
        JOIN framework_items i ON i.id = e.entity_id
        WHERE e.entity_type = 'framework_item' AND e.model_key = :key
          AND i.framework_id = ANY(:framework_ids)
    )
    SELECT entity_id, 1 - (vector <=> CAST(CAST(:query AS text) AS vector)) AS similarity
    FROM scope
    ORDER BY vector <=> CAST(CAST(:query AS text) AS vector)
    LIMIT :limit
    """
)

_KEYWORD_SQL = text(
    """
    WITH q AS (SELECT to_tsquery('simple', :query) AS query)
    SELECT i.id,
           ts_rank(to_tsvector('simple', i.title || ' ' || i.description), q.query) AS rank
    FROM framework_items i, q
    WHERE i.framework_id = ANY(:framework_ids)
      AND to_tsvector('simple', i.title || ' ' || i.description) @@ q.query
    ORDER BY rank DESC, i.code
    LIMIT :limit
    """
)

_STOP = frozenset(
    [
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "into",
        "their",
        "will",
        "able",
        "upon",
        "about",
        "which",
        "using",
        "use",
        "of",
        "to",
        "in",
        "die",
        "en",
        "van",
        "vir",
        "met",
        "wat",
        "dat",
        "'n",
        "ukuthi",
        "kwaye",
    ]
)


def keyword_query(value: str, *, most: int = 30) -> str | None:
    """An OR query of the distinct words (four letters or more) of a text, for ``to_tsquery``.

    The ``simple`` configuration does no stemming, so it works the same for English, Afrikaans
    and isiXhosa words."""
    words: list[str] = []
    for word in re.findall(r"\w{4,}", value.casefold()):
        if word not in _STOP and word not in words and not word.isdigit():
            words.append(word)
    if not words:
        return None
    return " | ".join(words[:most])


def _vector_literal(vector: Sequence[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


async def similar_framework_items(
    db: AsyncSession,
    settings: Settings,
    query: str,
    *,
    framework_ids: Sequence[uuid.UUID],
    limit: int = 20,
    provider: EmbeddingProvider | None = None,
    redis: Redis | None = None,
) -> Retrieved:
    """Framework items of the given frameworks that fit ``query``, best first.

    The query is curriculum text (an objective); the caller has already decided that it may
    be used. Meaning first; full-text with a notice when that is not possible."""
    if not framework_ids:
        return Retrieved([], Mode.MEANING)
    state = await embeddings_state(settings, redis)
    notice: Notice | None = None
    if state is EmbeddingsState.OFF:
        notice = Notice.EMBEDDINGS_OFF
    elif state is EmbeddingsState.UNREACHABLE:
        notice = Notice.EMBEDDINGS_UNREACHABLE
    else:
        embedder = provider or get_embedding_provider(settings)
        try:
            vector = (await embedder.embed([query]))[0]
        except ProviderError:
            logger.warning("retrieval_embedding_failed")
            notice = Notice.EMBEDDINGS_UNREACHABLE
        else:
            rows = (
                await db.execute(
                    _MEANING_SQL,
                    {
                        "key": MODEL_KEY,
                        "framework_ids": list(framework_ids),
                        "query": _vector_literal(vector),
                        "limit": limit,
                    },
                )
            ).all()
            if rows:
                return Retrieved([Hit(r[0], max(0.0, float(r[1]))) for r in rows], Mode.MEANING)
            notice = Notice.NOT_EMBEDDED_YET
    return Retrieved(await keyword_hits(db, query, framework_ids, limit), Mode.KEYWORD, notice)


async def keyword_hits(
    db: AsyncSession, query: str, framework_ids: Sequence[uuid.UUID], limit: int
) -> list[Hit]:
    expression = keyword_query(query)
    if expression is None:
        return []
    rows = (
        await db.execute(
            _KEYWORD_SQL,
            {"query": expression, "framework_ids": list(framework_ids), "limit": limit},
        )
    ).all()
    best = max((float(r[1]) for r in rows), default=0.0)
    return [Hit(r[0], float(r[1]) / best if best > 0 else 0.0) for r in rows]
