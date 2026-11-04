"""Searching the curriculum of one version (Slice 1.20, ADR 049).

Four kinds of thing are searched: objectives, learning events (sessions), modules and framework
items. Two signals are combined:

* **words**: PostgreSQL full-text search with the ``simple`` configuration (no stemming, so it
  behaves the same for English, Afrikaans and isiXhosa). Every word must match, the last one as a
  prefix (so "cardi" finds "cardiac"); when nothing matches every word, results that match some of
  the words are shown and the answer says so.
* **meaning**: the stored vectors of objectives and framework items (ADR 044). A query is embedded
  by the local server and compared with the vectors. Events and modules have no vectors of their
  own; they are found through their objectives. Without embeddings the search works on words
  alone and says so (a notice), exactly as the mapping shortlist does.

Everything a user sees is limited by what their roles show of the version (ADR 027,
``curriculum_read``): programme outcomes only to people who see the whole version, a module and
its outcomes to people who see the module, a session and its objectives to people who see it.
Not visible means not in the results, and counts never reveal hidden curriculum.

"Where do we teach X?" (``where_taught``) answers with sessions in schedule order (phase, module,
week, position), each with the objectives that matched and why.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import httpx
from redis.asyncio import Redis
from sqlalchemy import ColumnElement, Select, and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import MODEL_KEY, EmbeddingProvider, get_embedding_provider
from app.ai.errors import ProviderError
from app.core.config import Settings
from app.core.logging import get_logger
from app.models import (
    Framework,
    FrameworkItem,
    LearningEvent,
    MappingLink,
    Module,
    Objective,
    Phase,
    Tagging,
)
from app.models.curriculum import ObjectiveDomain, ObjectiveLevel, ObjectiveStatus
from app.models.framework import FrameworkStatus
from app.models.mapping import MappingStatus
from app.services.authorization import InvalidRequestError
from app.services.curriculum_read import VisibleVersion
from app.services.mapping_live import live_link
from app.services.retrieval import (
    EmbeddingsState,
    Mode,
    Notice,
    embeddings_state,
    similar_framework_items,
)

logger = get_logger(__name__)

QUERY_MIN = 2
QUERY_MAX = 200
DEFAULT_LIMIT = 10
MAX_LIMIT = 50
POOL = 200
MAX_WORDS = 12
# Items reached through the framework in "where do we teach": the best few item matches only.
FRAMEWORK_ITEMS_FOR_WHERE = 5
# How much of an objective's score its session or module inherits.
THROUGH = 0.9
FRAMEWORK_ROUTE = 0.8


class Kind(StrEnum):
    OBJECTIVE = "objective"
    EVENT = "event"
    MODULE = "module"
    FRAMEWORK_ITEM = "framework_item"


class Words(StrEnum):
    ALL = "all"  # every word of the query matched
    SOME = "some"  # nothing matched every word; results match some of them
    NONE = "none"  # nothing matched by words


@dataclass(frozen=True)
class Filters:
    phase_id: uuid.UUID | None = None
    module_id: uuid.UUID | None = None
    format_id: uuid.UUID | None = None
    tag_ids: tuple[uuid.UUID, ...] = ()
    framework_id: uuid.UUID | None = None
    taxonomy_level_id: uuid.UUID | None = None
    domain: ObjectiveDomain | None = None

    def applies_to(self) -> dict[Kind, bool]:
        """Which kinds of result the filters leave in. A filter that cannot describe a kind (a
        taxonomy level says nothing about a module) leaves that kind out."""
        about_objectives = self.taxonomy_level_id is not None or self.domain is not None
        return {
            Kind.OBJECTIVE: True,
            Kind.EVENT: not about_objectives and self.framework_id is None,
            Kind.MODULE: not about_objectives
            and self.format_id is None
            and self.framework_id is None,
            Kind.FRAMEWORK_ITEM: not about_objectives
            and self.phase_id is None
            and self.module_id is None
            and self.format_id is None
            and not self.tag_ids,
        }


@dataclass
class Hit:
    kind: Kind
    id: uuid.UUID
    title: str
    detail: str = ""
    score: float = 0.0
    # "words", "meaning", or "objective" (found through one of its objectives).
    matched_by: tuple[str, ...] = ()
    module_id: uuid.UUID | None = None
    module_code: str | None = None
    module_name: str | None = None
    phase_name: str | None = None
    event_id: uuid.UUID | None = None
    event_title: str | None = None
    week: int | None = None
    level: ObjectiveLevel | None = None
    domain: ObjectiveDomain | None = None
    framework_id: uuid.UUID | None = None
    framework_name: str | None = None
    code: str | None = None


@dataclass
class SearchResult:
    hits: dict[Kind, list[Hit]] = field(default_factory=dict)
    more: dict[Kind, bool] = field(default_factory=dict)
    words: Words = Words.NONE
    mode: Mode = Mode.KEYWORD
    notice: Notice | None = None
    # Kinds left out because a filter cannot describe them.
    left_out: list[Kind] = field(default_factory=list)


@dataclass(frozen=True)
class _ModuleRow:
    id: uuid.UUID
    code: str
    name: str
    description: str
    phase_id: uuid.UUID | None
    position: int


@dataclass(frozen=True)
class _EventRow:
    id: uuid.UUID
    module_id: uuid.UUID
    title: str
    description: str
    week: int | None
    position: int
    format_value_id: uuid.UUID | None


@dataclass
class _Scope:
    """What of the version the search may look at, after roles and filters."""

    visible: VisibleVersion
    # Modules the user sees whole (searched as modules; their outcomes are searched).
    modules: dict[uuid.UUID, _ModuleRow]
    # Every module that names a visible session, whole or only as context (for names).
    named: dict[uuid.UUID, _ModuleRow]
    events: dict[uuid.UUID, _EventRow]
    phases: dict[uuid.UUID, Phase]
    # The objectives roles and filters allow, as a query of ids.
    objective_ids: Select[Any]
    # With a tag filter: the modules and sessions that carry one of the tags (None: no filter).
    tagged_modules: set[uuid.UUID] | None = None
    tagged_events: set[uuid.UUID] | None = None


# --- The query -----------------------------------------------------------------------------


# Function words and question words: the ``simple`` configuration keeps them, so "where do we
# teach the heart" would match every text with "the" in it. They are left out of a query unless
# nothing else is left (English, with the few Afrikaans and isiXhosa words ADR 044 already skips).
STOP_WORDS = frozenset(
    [
        "a",
        "an",
        "the",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "at",
        "for",
        "with",
        "from",
        "into",
        "by",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "do",
        "does",
        "did",
        "how",
        "what",
        "where",
        "when",
        "why",
        "who",
        "which",
        "that",
        "this",
        "these",
        "those",
        "it",
        "its",
        "our",
        "we",
        "you",
        "your",
        "i",
        "me",
        "my",
        "us",
        "can",
        "could",
        "should",
        "would",
        "will",
        "shall",
        "may",
        "might",
        "about",
        "upon",
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


def query_words(value: str) -> list[str]:
    """The distinct words of a query (letters and digits), at most ``MAX_WORDS``. A single letter
    is dropped, a number is kept, and function words are dropped unless nothing else is left."""
    words: list[str] = []
    for word in re.findall(r"\w+", value.casefold()):
        if (len(word) >= QUERY_MIN or word.isdigit()) and word not in words:
            words.append(word)
    meaningful = [w for w in words if w not in STOP_WORDS]
    return (meaningful or words)[:MAX_WORDS]


def tsquery(words: list[str], *, every: bool) -> str | None:
    """A ``to_tsquery`` string: all words (the last one as a prefix) or any of them. The words
    are letters and digits only, so nothing in them can be query syntax."""
    parts = [re.sub(r"\W", "", w) for w in words]
    parts = [p for p in parts if p]
    if not parts:
        return None
    last = len(parts) - 1
    terms = [f"{p}:*" if i == last else p for i, p in enumerate(parts)]
    return (" & " if every else " | ").join(terms)


def check_query(value: str) -> str:
    """The query, trimmed; a query that is too short or too long is a plain refusal."""
    value = " ".join(value.split())
    if len(value) < QUERY_MIN:
        raise InvalidRequestError(f"Type at least {QUERY_MIN} characters to search.")
    if len(value) > QUERY_MAX:
        raise InvalidRequestError(f"Search for at most {QUERY_MAX} characters.")
    return value


# --- Scope ---------------------------------------------------------------------------------


async def _tagged(db: AsyncSession, tag_ids: tuple[uuid.UUID, ...], column: Any) -> set[uuid.UUID]:
    rows = await db.scalars(
        select(column).where(Tagging.tag_value_id.in_(tag_ids), column.is_not(None))
    )
    return {r for r in rows if r is not None}


async def _scope(db: AsyncSession, visible: VisibleVersion, filters: Filters) -> _Scope:
    view = visible.view
    version_id = visible.version.id
    phases = {
        p.id: p
        for p in await db.scalars(
            select(Phase).where(Phase.version_id == version_id, Phase.deleted_at.is_(None))
        )
    }
    modules: dict[uuid.UUID, _ModuleRow] = {}
    named: dict[uuid.UUID, _ModuleRow] = {}
    module_rows = await db.execute(
        select(
            Module.id,
            Module.code,
            Module.name,
            Module.description,
            Module.phase_id,
            Module.position,
        ).where(Module.version_id == version_id, Module.deleted_at.is_(None))
    )
    for values in module_rows:
        row = _ModuleRow(*values)
        if filters.phase_id is not None and row.phase_id != filters.phase_id:
            continue
        if filters.module_id is not None and row.id != filters.module_id:
            continue
        if view.shows_module(row.id):
            modules[row.id] = row
        named[row.id] = row

    events: dict[uuid.UUID, _EventRow] = {}
    if named:
        event_rows = await db.execute(
            select(
                LearningEvent.id,
                LearningEvent.module_id,
                LearningEvent.title,
                LearningEvent.description,
                LearningEvent.week,
                LearningEvent.position,
                LearningEvent.format_value_id,
            ).where(LearningEvent.module_id.in_(set(named)), LearningEvent.deleted_at.is_(None))
        )
        for event_values in event_rows:
            event = _EventRow(*event_values)
            if not view.shows_event(event.module_id, event.id):
                continue
            if filters.format_id is not None and event.format_value_id != filters.format_id:
                continue
            events[event.id] = event

    # Which objectives the roles and the filters allow.
    conditions: list[ColumnElement[bool]] = []
    narrowed = (
        filters.phase_id is not None
        or filters.module_id is not None
        or filters.format_id is not None
    )
    if view.full and not narrowed:
        conditions.append(Objective.level == ObjectiveLevel.PROGRAMME)
    if modules and filters.format_id is None:
        conditions.append(
            and_(Objective.level == ObjectiveLevel.MODULE, Objective.module_id.in_(set(modules)))
        )
    if events:
        conditions.append(
            and_(
                Objective.level == ObjectiveLevel.LEARNING_EVENT,
                Objective.learning_event_id.in_(set(events)),
            )
        )
    allowed = select(Objective.id).where(
        Objective.version_id == version_id,
        Objective.deleted_at.is_(None),
        Objective.status != ObjectiveStatus.RETIRED,
        or_(*conditions) if conditions else Objective.id.is_(None),
    )
    if filters.taxonomy_level_id is not None:
        allowed = allowed.where(Objective.taxonomy_level_id == filters.taxonomy_level_id)
    if filters.domain is not None:
        allowed = allowed.where(Objective.domain == filters.domain)
    scope = _Scope(visible, modules, named, events, phases, allowed)
    if filters.tag_ids:
        tagged_objectives = await _tagged(db, filters.tag_ids, Tagging.objective_id)
        scope.objective_ids = allowed.where(Objective.id.in_(tagged_objectives or {uuid.uuid4()}))
        scope.tagged_modules = await _tagged(db, filters.tag_ids, Tagging.module_id)
        scope.tagged_events = await _tagged(db, filters.tag_ids, Tagging.learning_event_id)
    if filters.framework_id is not None:
        linked = (
            select(MappingLink.objective_id)
            .join(FrameworkItem, FrameworkItem.id == MappingLink.framework_item_id)
            .where(
                FrameworkItem.framework_id == filters.framework_id,
                MappingLink.status != MappingStatus.REJECTED,
                live_link(),
            )
        )
        scope.objective_ids = scope.objective_ids.where(Objective.id.in_(linked))
    return scope


async def visible_objective_ids(
    db: AsyncSession, visible: VisibleVersion, filters: Filters | None = None
) -> Select[Any]:
    """A query of the ids of the live, non-retired objectives of a version that the user's
    roles show (and the filters allow). Reports use it so they never count what the user may
    not see (ADR 027)."""
    return (await _scope(db, visible, filters or Filters())).objective_ids


# --- Scores --------------------------------------------------------------------------------


# Results far below the best one are noise, and in "where do we teach" (listed in schedule
# order, not by score) a weak match would look as important as a strong one. A result is kept when
# its score is at least this much, or this share of the best score, whichever is higher.
KEEP_MIN = 0.12
KEEP_SHARE = 0.25


def keep_scores(scores: list[float]) -> float:
    """The lowest score worth showing among these."""
    return max(KEEP_MIN, KEEP_SHARE * max(scores, default=0.0))


def combine(words: float, meaning: float) -> float:
    """One score from the two signals (each 0 to 1): three quarters of the better one and a
    quarter of the other. A result both signals support outranks one that only one supports,
    and two strong signals cannot both reach the cap and lose their order."""
    return 0.75 * max(words, meaning) + 0.25 * min(words, meaning)


async def _words_found(
    db: AsyncSession,
    column: Any,
    id_column: Any,
    where: list[ColumnElement[bool]],
    words: list[str],
) -> tuple[dict[uuid.UUID, float], Words]:
    """Rows whose text matches every word, or (when none do) some of them; each scored 0 to 1
    against the best match."""
    for every in (True, False):
        expression = tsquery(words, every=every)
        if expression is None:
            break
        vector = func.to_tsvector("simple", column)
        query = func.to_tsquery("simple", expression)
        rank = func.ts_rank(vector, query)
        rows = (
            await db.execute(
                select(id_column, rank)
                .where(*where, vector.op("@@")(query))
                .order_by(rank.desc())
                .limit(POOL)
            )
        ).all()
        if rows:
            best = max(float(r[1]) for r in rows)
            scores = {r[0]: (float(r[1]) / best if best > 0 else 0.0) for r in rows}
            return scores, Words.ALL if every else Words.SOME
    return {}, Words.NONE


def _weakest(*modes: Words) -> Words:
    """The word match of a whole answer: "some" if any part had to fall back to some words."""
    found = [m for m in modes if m is not Words.NONE]
    if not found:
        return Words.NONE
    return Words.SOME if Words.SOME in found else Words.ALL


_OBJECTIVE_MEANING_SQL = text(
    """
    SELECT entity_id, 1 - (vector <=> CAST(CAST(:query AS text) AS vector)) AS similarity
    FROM embeddings
    WHERE entity_type = 'objective' AND model_key = :key AND entity_id = ANY(:ids)
    ORDER BY vector <=> CAST(CAST(:query AS text) AS vector)
    LIMIT :limit
    """
)


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


# A short query is compared with short texts, and the embedding model (ADR 044) gives unrelated
# ones a cosine of about 0.76 to 0.80 (a nonsense query reached 0.81), while good matches are
# 0.85 to 0.92. The mapping shortlist's floor of 0.75 (ADR 045) suits long texts and would list
# every session for every question, so search has its own, measured on the demo data on
# 2026-11-04 with ``MODEL_KEY``: changing the model means measuring again.
MEANING_FLOOR = 0.82
MEANING_SPAN = 0.08
# A meaning score below this is noise, not a result.
MEANING_MIN = 0.1


def _meaning_score(similarity: float) -> float:
    scaled = max(0.0, min(1.0, (similarity - MEANING_FLOOR) / MEANING_SPAN))
    return scaled if scaled >= MEANING_MIN else 0.0


async def _query_vector(
    settings: Settings,
    query: str,
    redis: Redis | None,
    embedder: EmbeddingProvider | None,
    transport: httpx.AsyncBaseTransport | None,
) -> tuple[list[float] | None, Notice | None]:
    state = await embeddings_state(settings, redis, transport)
    if state is EmbeddingsState.OFF:
        return None, Notice.EMBEDDINGS_OFF
    if state is EmbeddingsState.UNREACHABLE:
        return None, Notice.EMBEDDINGS_UNREACHABLE
    try:
        provider = embedder or get_embedding_provider(settings)
        return (await provider.embed([query]))[0], None
    except ProviderError:
        logger.warning("search_embedding_failed")
        return None, Notice.EMBEDDINGS_UNREACHABLE


@dataclass
class _Signals:
    words: dict[uuid.UUID, float]
    meaning: dict[uuid.UUID, float]
    mode: Words


async def _objective_signals(
    db: AsyncSession, scope: _Scope, words: list[str], vector: list[float] | None
) -> _Signals:
    found, mode = await _words_found(
        db, Objective.text, Objective.id, [Objective.id.in_(scope.objective_ids)], words
    )
    meaning: dict[uuid.UUID, float] = {}
    if vector is not None:
        ids = list(await db.scalars(scope.objective_ids))
        if ids:
            rows = (
                await db.execute(
                    _OBJECTIVE_MEANING_SQL,
                    {"key": MODEL_KEY, "ids": ids, "query": _vector_literal(vector), "limit": POOL},
                )
            ).all()
            for entity_id, similarity in rows:
                scaled = _meaning_score(float(similarity))
                if scaled > 0:
                    meaning[entity_id] = scaled
    return _Signals(found, meaning, mode)


# --- Hits ----------------------------------------------------------------------------------


def _place(
    scope: _Scope, module_id: uuid.UUID | None, event_id: uuid.UUID | None
) -> dict[str, object]:
    """Where in the curriculum something sits: its module, phase and session."""
    module = scope.named.get(module_id) if module_id else None
    phase = scope.phases.get(module.phase_id) if module and module.phase_id else None
    event = scope.events.get(event_id) if event_id else None
    return {
        "module_id": module_id,
        "module_code": module.code if module else None,
        "module_name": module.name if module else None,
        "phase_name": phase.name if phase else None,
        "event_id": event_id,
        "event_title": event.title if event else None,
        "week": event.week if event else None,
    }


def _schedule_key(
    scope: _Scope, module_id: uuid.UUID | None, event_id: uuid.UUID | None
) -> tuple[int, int, bool, int, int]:
    """Phase, module, week (sessions without one last), position: the order things are taught."""
    module = scope.named.get(module_id) if module_id else None
    phase = scope.phases.get(module.phase_id) if module and module.phase_id else None
    event = scope.events.get(event_id) if event_id else None
    return (
        phase.position if phase else 10_000,
        module.position if module else 10_000,
        event is None or event.week is None,
        (event.week or 0) if event else 0,
        event.position if event else 0,
    )


async def _objective_hits(
    db: AsyncSession, scope: _Scope, signals: _Signals
) -> dict[uuid.UUID, Hit]:
    ids = set(signals.words) | set(signals.meaning)
    if not ids:
        return {}
    hits: dict[uuid.UUID, Hit] = {}
    for o in await db.scalars(select(Objective).where(Objective.id.in_(ids))):
        w, m = signals.words.get(o.id, 0.0), signals.meaning.get(o.id, 0.0)
        event = scope.events.get(o.learning_event_id) if o.learning_event_id else None
        module_id = event.module_id if event else o.module_id
        hit = Hit(
            kind=Kind.OBJECTIVE,
            id=o.id,
            title=o.text,
            score=combine(w, m),
            matched_by=tuple(n for n, v in (("words", w), ("meaning", m)) if v > 0),
            level=o.level,
            domain=o.domain,
        )
        for name, value in _place(scope, module_id, event.id if event else None).items():
            setattr(hit, name, value)
        hits[o.id] = hit
    return hits


async def _event_hits(
    db: AsyncSession, scope: _Scope, words: list[str], objectives: dict[uuid.UUID, Hit]
) -> tuple[list[Hit], Words]:
    """Sessions whose title or description match, and sessions with a matching objective."""
    candidates = set(scope.events)
    if scope.tagged_events is not None:
        candidates &= scope.tagged_events
    found: dict[uuid.UUID, float] = {}
    mode = Words.NONE
    if candidates:
        found, mode = await _words_found(
            db,
            LearningEvent.title + " " + LearningEvent.description,
            LearningEvent.id,
            [LearningEvent.id.in_(candidates)],
            words,
        )
    through: dict[uuid.UUID, float] = {}
    for hit in objectives.values():
        if hit.event_id is not None and hit.event_id in candidates:
            through[hit.event_id] = max(through.get(hit.event_id, 0.0), hit.score * THROUGH)
    hits = []
    for event_id in set(found) | set(through):
        event = scope.events[event_id]
        direct, indirect = found.get(event_id, 0.0), through.get(event_id, 0.0)
        hit = Hit(
            kind=Kind.EVENT,
            id=event_id,
            title=event.title,
            detail=event.description,
            score=combine(direct, indirect),
            matched_by=tuple(n for n, v in (("words", direct), ("objective", indirect)) if v > 0),
        )
        for name, value in _place(scope, event.module_id, event_id).items():
            setattr(hit, name, value)
        hits.append(hit)
    return hits, mode


async def _module_hits(
    db: AsyncSession, scope: _Scope, words: list[str], objectives: dict[uuid.UUID, Hit]
) -> tuple[list[Hit], Words]:
    candidates = set(scope.modules)
    if scope.tagged_modules is not None:
        candidates &= scope.tagged_modules
    found: dict[uuid.UUID, float] = {}
    mode = Words.NONE
    if candidates:
        found, mode = await _words_found(
            db,
            Module.code + " " + Module.name + " " + Module.description,
            Module.id,
            [Module.id.in_(candidates)],
            words,
        )
    through: dict[uuid.UUID, float] = {}
    for hit in objectives.values():
        if hit.level is ObjectiveLevel.MODULE and hit.module_id in candidates:
            module_id = hit.module_id
            assert module_id is not None
            through[module_id] = max(through.get(module_id, 0.0), hit.score * THROUGH)
    hits = []
    for module_id in set(found) | set(through):
        module = scope.modules[module_id]
        direct, indirect = found.get(module_id, 0.0), through.get(module_id, 0.0)
        hit = Hit(
            kind=Kind.MODULE,
            id=module_id,
            title=f"{module.code} {module.name}",
            detail=module.description,
            score=combine(direct, indirect),
            matched_by=tuple(n for n, v in (("words", direct), ("objective", indirect)) if v > 0),
        )
        for name, value in _place(scope, module_id, None).items():
            setattr(hit, name, value)
        hits.append(hit)
    return hits, mode


async def _framework_hits(
    db: AsyncSession,
    settings: Settings,
    query: str,
    words: list[str],
    filters: Filters,
    use_meaning: bool,
    redis: Redis | None,
    embedder: EmbeddingProvider | None,
) -> tuple[list[Hit], Words]:
    frameworks = select(Framework.id, Framework.name).where(
        Framework.deleted_at.is_(None), Framework.status != FrameworkStatus.DRAFT
    )
    if filters.framework_id is not None:
        frameworks = frameworks.where(Framework.id == filters.framework_id)
    names = dict((await db.execute(frameworks)).all())
    if not names:
        return [], Words.NONE
    framework_ids = list(names)
    found, mode = await _words_found(
        db,
        FrameworkItem.code + " " + FrameworkItem.title + " " + FrameworkItem.description,
        FrameworkItem.id,
        [FrameworkItem.framework_id.in_(framework_ids)],
        words,
    )
    meaning: dict[uuid.UUID, float] = {}
    if use_meaning:
        retrieved = await similar_framework_items(
            db,
            settings,
            query,
            framework_ids=framework_ids,
            limit=POOL,
            provider=embedder,
            redis=redis,
        )
        if retrieved.mode is Mode.MEANING:
            for hit in retrieved.hits:
                scaled = _meaning_score(hit.score)
                if scaled > 0:
                    meaning[hit.item_id] = scaled
    ids = set(found) | set(meaning)
    if not ids:
        return [], mode
    hits = []
    for item in await db.scalars(select(FrameworkItem).where(FrameworkItem.id.in_(ids))):
        w, m = found.get(item.id, 0.0), meaning.get(item.id, 0.0)
        hits.append(
            Hit(
                kind=Kind.FRAMEWORK_ITEM,
                id=item.id,
                title=item.title,
                detail=item.description,
                score=combine(w, m),
                matched_by=tuple(n for n, v in (("words", w), ("meaning", m)) if v > 0),
                framework_id=item.framework_id,
                framework_name=names.get(item.framework_id),
                code=item.code,
            )
        )
    hits.sort(key=lambda h: (-h.score, h.code or ""))
    return hits, mode


# --- Search --------------------------------------------------------------------------------


async def search(
    db: AsyncSession,
    settings: Settings,
    visible: VisibleVersion,
    query: str,
    *,
    filters: Filters | None = None,
    kinds: frozenset[Kind] | None = None,
    frameworks_allowed: bool = True,
    limit: int = DEFAULT_LIMIT,
    mode: str = "auto",
    redis: Redis | None = None,
    embedder: EmbeddingProvider | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> SearchResult:
    """Search one version. ``frameworks_allowed`` is whether the user may read the framework
    library at all (it is shared by the institution and is not part of a version).

    Raises:
        InvalidRequestError: For a query that is too short or too long.
    """
    query = check_query(query)
    filters = filters or Filters()
    limit = max(1, min(limit, MAX_LIMIT))
    asked = kinds or frozenset(Kind)
    applies = filters.applies_to()
    result = SearchResult()
    result.left_out = [k for k in Kind if k in asked and not applies[k]]
    wanted = {k for k in asked if applies[k]}
    if not frameworks_allowed:
        wanted.discard(Kind.FRAMEWORK_ITEM)

    scope = await _scope(db, visible, filters)
    words = query_words(query)
    vector: list[float] | None = None
    if mode != "words":
        vector, result.notice = await _query_vector(settings, query, redis, embedder, transport)
    if vector is not None:
        result.mode = Mode.MEANING

    signals = await _objective_signals(db, scope, words, vector)
    objectives = await _objective_hits(db, scope, signals)
    modes = [signals.mode]
    if vector is not None and not signals.meaning and result.notice is None:
        # The server answers but no objective has a vector yet (embed-all has not been run).
        result.notice = Notice.NOT_EMBEDDED_YET

    if Kind.OBJECTIVE in wanted:
        floor = keep_scores([h.score for h in objectives.values()])
        ordered = sorted(
            (h for h in objectives.values() if h.score >= floor), key=lambda h: (-h.score, h.title)
        )
        result.hits[Kind.OBJECTIVE] = ordered[:limit]
        result.more[Kind.OBJECTIVE] = len(ordered) > limit
    if Kind.EVENT in wanted:
        events, event_mode = await _event_hits(db, scope, words, objectives)
        modes.append(event_mode)
        floor = keep_scores([h.score for h in events])
        events = [h for h in events if h.score >= floor]
        events.sort(
            key=lambda h: (-h.score, _schedule_key(scope, h.module_id, h.event_id), h.title)
        )
        result.hits[Kind.EVENT] = events[:limit]
        result.more[Kind.EVENT] = len(events) > limit
    if Kind.MODULE in wanted:
        modules, module_mode = await _module_hits(db, scope, words, objectives)
        modes.append(module_mode)
        floor = keep_scores([h.score for h in modules])
        modules = [h for h in modules if h.score >= floor]
        modules.sort(key=lambda h: (-h.score, h.module_code or ""))
        result.hits[Kind.MODULE] = modules[:limit]
        result.more[Kind.MODULE] = len(modules) > limit
    if Kind.FRAMEWORK_ITEM in wanted:
        items, item_mode = await _framework_hits(
            db, settings, query, words, filters, vector is not None, redis, embedder
        )
        modes.append(item_mode)
        result.hits[Kind.FRAMEWORK_ITEM] = items[:limit]
        result.more[Kind.FRAMEWORK_ITEM] = len(items) > limit
    result.words = _weakest(*modes)
    return result


# --- Where do we teach X? -------------------------------------------------------------------


@dataclass
class TaughtObjective:
    id: uuid.UUID
    text: str
    level: ObjectiveLevel
    score: float
    via: str


@dataclass
class TaughtIn:
    event_id: uuid.UUID | None
    event_title: str | None
    week: int | None
    module_id: uuid.UUID
    module_code: str
    module_name: str
    phase_name: str | None
    score: float = 0.0
    # Why this is listed: "title" (its title or description), "objective" (words), "meaning",
    # or "framework <CODE>" (an objective accepted for a framework item the question matched).
    why: list[str] = field(default_factory=list)
    objectives: list[TaughtObjective] = field(default_factory=list)


@dataclass
class WhereTaught:
    # Sessions in schedule order; module-level matches have no session.
    sessions: list[TaughtIn]
    modules: list[TaughtIn]
    words: Words
    mode: Mode
    notice: Notice | None
    # Framework items the question also matched, whose accepted links were followed.
    items: list[Hit]
    more: bool = False


async def where_taught(
    db: AsyncSession,
    settings: Settings,
    visible: VisibleVersion,
    query: str,
    *,
    filters: Filters | None = None,
    frameworks_allowed: bool = True,
    limit: int = 30,
    redis: Redis | None = None,
    embedder: EmbeddingProvider | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> WhereTaught:
    """Sessions that teach something that matches ``query``, in schedule order.

    Raises:
        InvalidRequestError: For a query that is too short or too long.
    """
    query = check_query(query)
    filters = filters or Filters()
    scope = await _scope(db, visible, filters)
    words = query_words(query)
    vector, notice = await _query_vector(settings, query, redis, embedder, transport)
    signals = await _objective_signals(db, scope, words, vector)
    objectives = await _objective_hits(db, scope, signals)
    modes = [signals.mode]

    rows: dict[tuple[uuid.UUID, uuid.UUID | None], TaughtIn] = {}

    def row(module_id: uuid.UUID, event_id: uuid.UUID | None) -> TaughtIn | None:
        module = scope.named.get(module_id)
        if module is None:
            return None
        key = (module_id, event_id)
        if key not in rows:
            event = scope.events.get(event_id) if event_id else None
            phase = scope.phases.get(module.phase_id) if module.phase_id else None
            rows[key] = TaughtIn(
                event_id=event_id,
                event_title=event.title if event else None,
                week=event.week if event else None,
                module_id=module_id,
                module_code=module.code,
                module_name=module.name,
                phase_name=phase.name if phase else None,
            )
        return rows[key]

    def add(
        target: TaughtIn | None,
        objective: tuple[uuid.UUID, str, ObjectiveLevel] | None,
        why: str,
        score: float,
    ) -> None:
        if target is None:
            return
        target.score = max(target.score, score)
        if why not in target.why:
            target.why.append(why)
        if objective is not None and all(o.id != objective[0] for o in target.objectives):
            target.objectives.append(
                TaughtObjective(objective[0], objective[1], objective[2], score, why)
            )

    for hit in objectives.values():
        if hit.level is None or hit.level is ObjectiveLevel.PROGRAMME:
            continue
        why = "meaning" if hit.matched_by == ("meaning",) else "objective"
        detail: tuple[uuid.UUID, str, ObjectiveLevel] = (hit.id, hit.title, hit.level)
        if hit.level is ObjectiveLevel.LEARNING_EVENT and hit.event_id and hit.module_id:
            add(row(hit.module_id, hit.event_id), detail, why, hit.score)
        elif hit.level is ObjectiveLevel.MODULE and hit.module_id:
            add(row(hit.module_id, None), detail, why, hit.score)

    # Sessions whose own title or description match.
    candidates = set(scope.events)
    if scope.tagged_events is not None:
        candidates &= scope.tagged_events
    if candidates:
        found, title_mode = await _words_found(
            db,
            LearningEvent.title + " " + LearningEvent.description,
            LearningEvent.id,
            [LearningEvent.id.in_(candidates)],
            words,
        )
        modes.append(title_mode)
        for event_id, score in found.items():
            add(row(scope.events[event_id].module_id, event_id), None, "title", score)

    # The framework route: items the question matches, and the objectives accepted for them.
    items: list[Hit] = []
    if frameworks_allowed:
        found_items, item_mode = await _framework_hits(
            db, settings, query, words, filters, vector is not None, redis, embedder
        )
        modes.append(item_mode)
        items = found_items[:FRAMEWORK_ITEMS_FOR_WHERE]
        by_id = {i.id: i for i in items}
        if by_id:
            linked = (
                await db.execute(
                    select(MappingLink.framework_item_id, Objective)
                    .join(Objective, Objective.id == MappingLink.objective_id)
                    .where(
                        MappingLink.framework_item_id.in_(set(by_id)),
                        MappingLink.status == MappingStatus.ACCEPTED,
                        live_link(),
                        Objective.id.in_(scope.objective_ids),
                    )
                )
            ).all()
            for item_id, objective in linked:
                why = f"framework {by_id[item_id].code}"
                score = by_id[item_id].score * FRAMEWORK_ROUTE
                found_detail: tuple[uuid.UUID, str, ObjectiveLevel] = (
                    objective.id,
                    objective.text,
                    objective.level,
                )
                event = (
                    scope.events.get(objective.learning_event_id)
                    if objective.learning_event_id
                    else None
                )
                if event is not None:
                    add(row(event.module_id, event.id), found_detail, why, score)
                elif objective.level is ObjectiveLevel.MODULE and objective.module_id:
                    add(row(objective.module_id, None), found_detail, why, score)

    floor = keep_scores([r.score for r in rows.values()])
    rows = {key: r for key, r in rows.items() if r.score >= floor}
    for target in rows.values():
        target.objectives = [o for o in target.objectives if o.score >= floor]
        target.objectives.sort(key=lambda o: -o.score)
    sessions = sorted(
        (r for r in rows.values() if r.event_id is not None),
        key=lambda r: _schedule_key(scope, r.module_id, r.event_id),
    )
    modules = sorted(
        (r for r in rows.values() if r.event_id is None),
        key=lambda r: _schedule_key(scope, r.module_id, None),
    )
    return WhereTaught(
        sessions=sessions[:limit],
        modules=modules[:limit],
        words=_weakest(*modes),
        mode=Mode.MEANING if vector is not None else Mode.KEYWORD,
        notice=notice,
        items=items,
        more=len(sessions) > limit,
    )
