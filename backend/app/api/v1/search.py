"""Search a curriculum version and answer "Where do we teach X?" (Slice 1.20, ADR 049).

Anyone who can see a version may search it; they find only what their roles show of it (ADR 027).
A version the user cannot see is a 404. Framework items are shared by the institution and are
searched only for people who may read the framework library (ADR 038). Meaning-based matching
uses the local embeddings server when it is on; without it the answer says so and uses words
alone.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import CurrentUser, RedisDep, SettingsDep, too_many_attempts
from app.api.v1.curriculum import Access
from app.core.database import DbSession
from app.models import (
    Framework,
    LearningEvent,
    Module,
    Phase,
    TagList,
    TagValue,
    TaxonomyLevel,
    TaxonomyScale,
)
from app.models.curriculum import ObjectiveDomain, ObjectiveLevel
from app.models.framework import FrameworkStatus
from app.services import rate_limit, search
from app.services.curriculum_read import VisibleVersion, visible_version
from app.services.framework_browse import may_read_frameworks
from app.services.retrieval import Mode, Notice
from app.services.search import Filters, Kind, Words

router = APIRouter(tags=["search"])

_SCOPE = "search"
SEARCHES_PER_MINUTE = 120
DETAIL_CUT = 300


class HitRead(BaseModel):
    kind: Kind
    id: uuid.UUID
    title: str
    detail: str
    score: float
    matched_by: list[str]
    module_id: uuid.UUID | None
    module_code: str | None
    module_name: str | None
    phase_name: str | None
    event_id: uuid.UUID | None
    event_title: str | None
    week: int | None
    level: ObjectiveLevel | None
    domain: ObjectiveDomain | None
    framework_id: uuid.UUID | None
    framework_name: str | None
    code: str | None


class GroupRead(BaseModel):
    kind: Kind
    hits: list[HitRead]
    more: bool


class SearchRead(BaseModel):
    query: str
    # "all": every word matched; "some": nothing matched every word, so these match some of them.
    words: Words
    mode: Mode
    notice: Notice | None
    # Kinds left out because a filter cannot describe them (a taxonomy level and a module).
    left_out: list[Kind]
    groups: list[GroupRead]


class TaughtObjectiveRead(BaseModel):
    id: uuid.UUID
    text: str
    level: ObjectiveLevel
    score: float
    via: str


class TaughtInRead(BaseModel):
    event_id: uuid.UUID | None
    event_title: str | None
    week: int | None
    module_id: uuid.UUID
    module_code: str
    module_name: str
    phase_name: str | None
    score: float
    why: list[str]
    objectives: list[TaughtObjectiveRead]


class WhereTaughtRead(BaseModel):
    query: str
    words: Words
    mode: Mode
    notice: Notice | None
    sessions: list[TaughtInRead]
    modules: list[TaughtInRead]
    framework_items: list[HitRead]
    more: bool


class Option(BaseModel):
    id: uuid.UUID
    label: str


class TagListOption(BaseModel):
    id: uuid.UUID
    name: str
    values: list[Option]


class ModuleOption(BaseModel):
    id: uuid.UUID
    label: str
    phase_id: uuid.UUID | None


class FilterOptions(BaseModel):
    phases: list[Option]
    modules: list[ModuleOption]
    formats: list[Option]
    tag_lists: list[TagListOption]
    frameworks: list[Option]
    taxonomy_levels: list[Option]
    domains: list[ObjectiveDomain]


def _hit(hit: search.Hit) -> HitRead:
    return HitRead(
        kind=hit.kind,
        id=hit.id,
        title=hit.title,
        detail=hit.detail[:DETAIL_CUT],
        score=round(hit.score, 3),
        matched_by=list(hit.matched_by),
        module_id=hit.module_id,
        module_code=hit.module_code,
        module_name=hit.module_name,
        phase_name=hit.phase_name,
        event_id=hit.event_id,
        event_title=hit.event_title,
        week=hit.week,
        level=hit.level,
        domain=hit.domain,
        framework_id=hit.framework_id,
        framework_name=hit.framework_name,
        code=hit.code,
    )


def _taught(row: search.TaughtIn) -> TaughtInRead:
    return TaughtInRead(
        event_id=row.event_id,
        event_title=row.event_title,
        week=row.week,
        module_id=row.module_id,
        module_code=row.module_code,
        module_name=row.module_name,
        phase_name=row.phase_name,
        score=round(row.score, 3),
        why=row.why,
        objectives=[
            TaughtObjectiveRead(
                id=o.id, text=o.text, level=o.level, score=round(o.score, 3), via=o.via
            )
            for o in row.objectives
        ],
    )


async def _visible(db: DbSession, access: Access, version_id: uuid.UUID) -> VisibleVersion:
    visible = await visible_version(db, access, version_id)
    if visible is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Curriculum version not found.")
    return visible


async def _limit(redis: RedisDep, actor: CurrentUser) -> None:
    limited = await rate_limit.check(redis, _SCOPE, str(actor.id), SEARCHES_PER_MINUTE)
    if not limited.allowed:
        raise too_many_attempts(limited.retry_after_seconds)
    await rate_limit.hit(redis, _SCOPE, str(actor.id), 60)


def _filters(
    phase_id: uuid.UUID | None,
    module_id: uuid.UUID | None,
    format_id: uuid.UUID | None,
    tag_id: list[uuid.UUID] | None,
    framework_id: uuid.UUID | None,
    taxonomy_level_id: uuid.UUID | None,
    domain: ObjectiveDomain | None,
) -> Filters:
    return Filters(
        phase_id=phase_id,
        module_id=module_id,
        format_id=format_id,
        tag_ids=tuple(tag_id or ()),
        framework_id=framework_id,
        taxonomy_level_id=taxonomy_level_id,
        domain=domain,
    )


@router.get("/curriculum-versions/{version_id}/search", response_model=SearchRead)
async def search_version(
    version_id: uuid.UUID,
    access: Access,
    actor: CurrentUser,
    db: DbSession,
    redis: RedisDep,
    settings: SettingsDep,
    q: Annotated[str, Query(max_length=1000)],
    types: Annotated[list[Kind] | None, Query()] = None,
    mode: Annotated[str, Query(pattern="^(auto|words)$")] = "auto",
    phase_id: uuid.UUID | None = None,
    module_id: uuid.UUID | None = None,
    format_id: uuid.UUID | None = None,
    tag_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    framework_id: uuid.UUID | None = None,
    taxonomy_level_id: uuid.UUID | None = None,
    domain: ObjectiveDomain | None = None,
    limit: Annotated[int, Query(ge=1, le=search.MAX_LIMIT)] = search.DEFAULT_LIMIT,
) -> SearchRead:
    """Objectives, sessions, modules and framework items that fit the words or the meaning of
    ``q``, best first, grouped by kind."""
    visible = await _visible(db, access, version_id)
    await _limit(redis, actor)
    result = await search.search(
        db,
        settings,
        visible,
        q,
        filters=_filters(
            phase_id, module_id, format_id, tag_id, framework_id, taxonomy_level_id, domain
        ),
        kinds=frozenset(types) if types else None,
        frameworks_allowed=may_read_frameworks(access),
        limit=limit,
        mode=mode,
        redis=redis,
    )
    return SearchRead(
        query=search.check_query(q),
        words=result.words,
        mode=result.mode,
        notice=result.notice,
        left_out=result.left_out,
        groups=[
            GroupRead(kind=kind, hits=[_hit(h) for h in hits], more=result.more.get(kind, False))
            for kind, hits in result.hits.items()
        ],
    )


@router.get("/curriculum-versions/{version_id}/where-taught", response_model=WhereTaughtRead)
async def where_taught(
    version_id: uuid.UUID,
    access: Access,
    actor: CurrentUser,
    db: DbSession,
    redis: RedisDep,
    settings: SettingsDep,
    q: Annotated[str, Query(max_length=1000)],
    phase_id: uuid.UUID | None = None,
    module_id: uuid.UUID | None = None,
    format_id: uuid.UUID | None = None,
    tag_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> WhereTaughtRead:
    """ "Where do we teach X?": the sessions (and modules) that teach it, in the order they are
    taught, each with the objectives that matched and why."""
    visible = await _visible(db, access, version_id)
    await _limit(redis, actor)
    found = await search.where_taught(
        db,
        settings,
        visible,
        q,
        filters=_filters(phase_id, module_id, format_id, tag_id, None, None, None),
        frameworks_allowed=may_read_frameworks(access),
        limit=limit,
        redis=redis,
    )
    return WhereTaughtRead(
        query=search.check_query(q),
        words=found.words,
        mode=found.mode,
        notice=found.notice,
        sessions=[_taught(r) for r in found.sessions],
        modules=[_taught(r) for r in found.modules],
        framework_items=[_hit(h) for h in found.items],
        more=found.more,
    )


@router.get("/curriculum-versions/{version_id}/search-filters", response_model=FilterOptions)
async def search_filters(version_id: uuid.UUID, access: Access, db: DbSession) -> FilterOptions:
    """What the filters of the search screen can be set to, for the parts of this version the
    user sees."""
    visible = await _visible(db, access, version_id)
    view = visible.view
    phases = await db.execute(
        select(Phase.id, Phase.name)
        .where(Phase.version_id == version_id, Phase.deleted_at.is_(None))
        .order_by(Phase.position)
    )
    modules = [
        ModuleOption(id=m.id, label=f"{m.code} {m.name}", phase_id=m.phase_id)
        for m in await db.execute(
            select(Module.id, Module.code, Module.name, Module.phase_id)
            .where(Module.version_id == version_id, Module.deleted_at.is_(None))
            .order_by(Module.position)
        )
        if view.shows_module(m.id)
    ]
    formats = await db.execute(
        select(TagValue.id, TagValue.label)
        .where(
            TagValue.id.in_(
                select(LearningEvent.format_value_id)
                .join(Module, Module.id == LearningEvent.module_id)
                .where(
                    Module.version_id == version_id,
                    LearningEvent.deleted_at.is_(None),
                    LearningEvent.format_value_id.is_not(None),
                )
            )
        )
        .order_by(TagValue.label)
    )
    tag_lists = []
    for tag_list in await db.scalars(
        select(TagList)
        .where(TagList.deleted_at.is_(None), TagList.is_active.is_(True))
        .order_by(TagList.name)
    ):
        values = [
            Option(id=v.id, label=v.label)
            for v in await db.scalars(
                select(TagValue)
                .where(TagValue.tag_list_id == tag_list.id, TagValue.is_active.is_(True))
                .order_by(TagValue.position, TagValue.label)
            )
        ]
        if values:
            tag_lists.append(TagListOption(id=tag_list.id, name=tag_list.name, values=values))
    frameworks: list[Option] = []
    if may_read_frameworks(access):
        frameworks = [
            Option(id=f.id, label=f.name)
            for f in await db.scalars(
                select(Framework)
                .where(Framework.deleted_at.is_(None), Framework.status != FrameworkStatus.DRAFT)
                .order_by(Framework.name)
            )
        ]
    levels = [
        Option(id=level.id, label=f"{scale} · {level.name}")
        for level, scale in await db.execute(
            select(TaxonomyLevel, TaxonomyScale.name)
            .join(TaxonomyScale, TaxonomyScale.id == TaxonomyLevel.scale_id)
            .order_by(TaxonomyScale.name, TaxonomyLevel.position)
        )
    ]
    return FilterOptions(
        phases=[Option(id=i, label=n) for i, n in phases],
        modules=modules,
        formats=[Option(id=i, label=n) for i, n in formats],
        tag_lists=tag_lists,
        frameworks=frameworks,
        taxonomy_levels=levels,
        domains=list(ObjectiveDomain),
    )
