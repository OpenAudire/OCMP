"""Tests for tag lists, tag values, taggings and teaching formats."""

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LearningEvent, Module, Tagging, TagList, TagValue
from app.models.tagging import TagListKind
from app.services.authorization import ConflictError, InvalidRequestError
from app.services.curriculum import add_objective
from app.services.tagging import (
    add_tag_value,
    item_taggings,
    remove_tagging,
    set_teaching_format,
    tag_item,
)
from tests.factories import LearningEventFactory, ModuleFactory, ProgrammeFactory, TagListFactory

pytestmark = pytest.mark.filterwarnings(
    "ignore:Object of type .* not in session:sqlalchemy.exc.SAWarning"
)


async def save(db: AsyncSession, *objects: object) -> None:
    db.add_all(objects)
    await db.flush()


async def must_fail(db: AsyncSession, *objects: object) -> None:
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            db.add_all(objects)
            await db.flush()


async def new_list(db: AsyncSession, **kwargs: object) -> TagList:
    tag_list = TagListFactory(**kwargs)
    await save(db, tag_list)
    return tag_list


@pytest.fixture
async def event(db_session: AsyncSession) -> LearningEvent:
    event = LearningEventFactory()
    await save(db_session, event)
    return event


class TestTagLists:
    async def test_defaults_allow_every_item_type(self, db_session: AsyncSession) -> None:
        tag_list = await new_list(db_session)

        assert set(tag_list.entity_types) == {"programme", "module", "learning_event", "objective"}
        assert tag_list.is_active

    @pytest.mark.parametrize("key", ["Has Space", "UPPER"])
    async def test_key_format(self, db_session: AsyncSession, key: str) -> None:
        await must_fail(db_session, TagListFactory(key=key))

    async def test_key_unique_among_live_lists(self, db_session: AsyncSession) -> None:
        first = await new_list(db_session, key="themes")

        await must_fail(db_session, TagListFactory(key="themes"))
        first.soft_delete()
        await db_session.flush()
        await new_list(db_session, key="themes")


class TestValues:
    async def test_values_unique_by_label_and_code(self, db_session: AsyncSession) -> None:
        tag_list = await new_list(db_session)
        other = await new_list(db_session)
        await add_tag_value(db_session, tag_list, "  OSCE ", code="osce")

        with pytest.raises(ConflictError, match="already in this list"):
            await add_tag_value(db_session, tag_list, "OSCE")
        with pytest.raises(ConflictError, match="Code"):
            await add_tag_value(db_session, tag_list, "Objective structured exam", code="osce")
        await add_tag_value(db_session, other, "OSCE", code="osce")  # other list: fine

    async def test_database_enforces_label_uniqueness(self, db_session: AsyncSession) -> None:
        tag_list = await new_list(db_session)
        await add_tag_value(db_session, tag_list, "MCQ")

        await must_fail(db_session, TagValue(tag_list_id=tag_list.id, label="MCQ"))

    async def test_blank_label_and_deleted_list(self, db_session: AsyncSession) -> None:
        tag_list = await new_list(db_session)

        with pytest.raises(InvalidRequestError, match="label"):
            await add_tag_value(db_session, tag_list, "   ")
        tag_list.soft_delete()
        with pytest.raises(InvalidRequestError, match="deleted"):
            await add_tag_value(db_session, tag_list, "Anything")


class TestTaggings:
    async def test_tag_each_kind_of_item(
        self, db_session: AsyncSession, event: LearningEvent
    ) -> None:
        theme = await add_tag_value(db_session, await new_list(db_session), "Ethics")
        module = await db_session.get(Module, event.module_id)
        assert module is not None
        programme = ProgrammeFactory()
        await save(db_session, programme)
        objective = await add_objective(db_session, event, "Obtain informed consent.")

        for item in (programme, module, event, objective):
            tagging = await tag_item(db_session, theme, item)
            assert not tagging.is_inherited
            assert [t.tag_value.label for t in await item_taggings(db_session, item)] == ["Ethics"]

    async def test_list_limited_to_some_item_types(
        self, db_session: AsyncSession, event: LearningEvent
    ) -> None:
        methods = await new_list(
            db_session,
            name="Assessment methods",
            kind="assessment_method",
            entity_types=["module", "objective"],
        )
        osce = await add_tag_value(db_session, methods, "OSCE")

        with pytest.raises(InvalidRequestError, match="cannot be used on a learning_event"):
            await tag_item(db_session, osce, event)

    async def test_duplicate_tag(self, db_session: AsyncSession, event: LearningEvent) -> None:
        value = await add_tag_value(db_session, await new_list(db_session), "Ethics")
        await tag_item(db_session, value, event)

        with pytest.raises(ConflictError):
            await tag_item(db_session, value, event)

    async def test_unavailable_tags_cannot_be_applied(
        self, db_session: AsyncSession, event: LearningEvent
    ) -> None:
        tag_list = await new_list(db_session)
        value = await add_tag_value(db_session, tag_list, "Retired tag")

        value.is_active = False
        with pytest.raises(InvalidRequestError, match="tag is not available"):
            await tag_item(db_session, value, event)
        value.is_active = True
        tag_list.is_active = False
        with pytest.raises(InvalidRequestError, match="list is not available"):
            await tag_item(db_session, value, event)

    async def test_deleted_item_cannot_be_tagged(
        self, db_session: AsyncSession, event: LearningEvent
    ) -> None:
        value = await add_tag_value(db_session, await new_list(db_session), "Ethics")
        event.soft_delete()

        with pytest.raises(InvalidRequestError, match="deleted item"):
            await tag_item(db_session, value, event)

    async def test_exactly_one_item_per_tagging(
        self, db_session: AsyncSession, event: LearningEvent
    ) -> None:
        value = await add_tag_value(db_session, await new_list(db_session), "Ethics")

        await must_fail(db_session, Tagging(tag_value_id=value.id))
        await must_fail(
            db_session,
            Tagging(tag_value_id=value.id, learning_event_id=event.id, module_id=event.module_id),
        )

    async def test_deleting_an_item_removes_its_tags(
        self, db_session: AsyncSession, event: LearningEvent
    ) -> None:
        value = await add_tag_value(db_session, await new_list(db_session), "Ethics")
        await tag_item(db_session, value, event)

        await db_session.execute(delete(LearningEvent).where(LearningEvent.id == event.id))

        assert (await db_session.execute(select(Tagging))).first() is None


class TestInheritance:
    async def test_inherited_tags_follow_their_source(self, db_session: AsyncSession) -> None:
        module = ModuleFactory()
        sessions = [LearningEventFactory(module=module) for _ in range(2)]
        await save(db_session, module, *sessions)
        value = await add_tag_value(db_session, await new_list(db_session), "Professionalism")
        source = await tag_item(db_session, value, module)

        inherited = [await tag_item(db_session, value, s, inherited_from=source) for s in sessions]
        assert all(t.is_inherited and t.inherited_from_id == source.id for t in inherited)

        # A direct tag can sit alongside an inherited one.
        await tag_item(db_session, value, sessions[0])
        with pytest.raises(ConflictError):
            await tag_item(db_session, value, sessions[1], inherited_from=source)

        with pytest.raises(InvalidRequestError, match="inherited"):
            await remove_tagging(db_session, inherited[0])

        await remove_tagging(db_session, source)
        remaining = (await db_session.execute(select(Tagging))).scalars().all()
        assert len(remaining) == 1  # only the direct tag on the first session
        assert remaining[0].learning_event_id == sessions[0].id
        assert not remaining[0].is_inherited

    async def test_inherited_tag_must_match_source(
        self, db_session: AsyncSession, event: LearningEvent
    ) -> None:
        tag_list = await new_list(db_session)
        ethics = await add_tag_value(db_session, tag_list, "Ethics")
        safety = await add_tag_value(db_session, tag_list, "Safety")
        module = await db_session.get(Module, event.module_id)
        assert module is not None
        source = await tag_item(db_session, ethics, module)

        with pytest.raises(InvalidRequestError, match="same tag"):
            await tag_item(db_session, safety, event, inherited_from=source)


class TestTeachingFormat:
    async def test_format_comes_from_teaching_method_list(
        self, db_session: AsyncSession, event: LearningEvent
    ) -> None:
        methods = await new_list(db_session, kind=TagListKind.TEACHING_METHOD)
        pbl = await add_tag_value(db_session, methods, "PBL tutorial")
        themes = await new_list(db_session, kind=TagListKind.THEME)
        ethics = await add_tag_value(db_session, themes, "Ethics")

        await set_teaching_format(db_session, event, pbl)
        assert event.format_value_id == pbl.id

        with pytest.raises(InvalidRequestError, match="teaching-method"):
            await set_teaching_format(db_session, event, ethics)

        await set_teaching_format(db_session, event, None)
        assert event.format_value_id is None

    async def test_removing_format_value_clears_events(
        self, db_session: AsyncSession, event: LearningEvent
    ) -> None:
        methods = await new_list(db_session, kind=TagListKind.TEACHING_METHOD)
        lecture = await add_tag_value(db_session, methods, "Lecture")
        await set_teaching_format(db_session, event, lecture)

        await db_session.execute(delete(TagValue).where(TagValue.id == lecture.id))
        await db_session.refresh(event)

        assert event.format_value_id is None
