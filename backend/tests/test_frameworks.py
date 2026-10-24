"""Tests for frameworks, framework items, cross-references, crosswalks and taxonomy scales."""

import json
from pathlib import Path

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Crosswalk,
    Framework,
    FrameworkCrossRef,
    FrameworkItem,
    Objective,
    TaxonomyLevel,
    TaxonomyScale,
)
from app.models.framework import (
    CrossRefType,
    CrosswalkEntryType,
    FrameworkProfile,
    FrameworkStatus,
)
from app.services.authorization import ConflictError, InvalidRequestError
from app.services.curriculum import add_objective
from app.services.frameworks import (
    activate_framework,
    add_cross_ref,
    add_crosswalk_entry,
    add_item,
)
from tests.factories import FrameworkFactory, ModuleFactory, TaxonomyScaleFactory

DEMO_PACK = (
    Path(__file__).resolve().parents[2] / "packs" / "demo" / "demo-graduate-competencies.json"
)

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


@pytest.fixture
async def framework(db_session: AsyncSession) -> Framework:
    framework = FrameworkFactory()
    await save(db_session, framework)
    return framework


class TestTaxonomyScales:
    async def test_levels_are_ordered_with_verbs(self, db_session: AsyncSession) -> None:
        scale = TaxonomyScaleFactory(key="miller")
        await save(db_session, scale)
        for position, name in [(2, "Shows how"), (0, "Knows"), (3, "Does"), (1, "Knows how")]:
            db_session.add(
                TaxonomyLevel(scale_id=scale.id, position=position, name=name, verbs=["x"])
            )
        await db_session.flush()
        db_session.expunge_all()

        loaded = (
            await db_session.execute(
                select(TaxonomyScale)
                .where(TaxonomyScale.key == "miller")
                .options(selectinload(TaxonomyScale.levels))
            )
        ).scalar_one()

        assert [level.name for level in loaded.levels] == [
            "Knows",
            "Knows how",
            "Shows how",
            "Does",
        ]

    async def test_level_positions_and_names_unique_in_scale(
        self, db_session: AsyncSession
    ) -> None:
        scale = TaxonomyScaleFactory()
        await save(db_session, scale)
        await save(db_session, TaxonomyLevel(scale_id=scale.id, position=0, name="A"))

        await must_fail(db_session, TaxonomyLevel(scale_id=scale.id, position=0, name="B"))
        await must_fail(db_session, TaxonomyLevel(scale_id=scale.id, position=1, name="A"))

    async def test_objective_taxonomy_level(self, db_session: AsyncSession) -> None:
        scale = TaxonomyScaleFactory()
        module = ModuleFactory()
        await save(db_session, scale, module)
        apply_level = TaxonomyLevel(scale_id=scale.id, position=2, name="Apply")
        await save(db_session, apply_level)
        objective = await add_objective(db_session, module, "Calculate a drug dose.")
        objective.taxonomy_level_id = apply_level.id
        await db_session.flush()

        # Removing the scale clears the objective's level instead of deleting the objective.
        await db_session.execute(delete(TaxonomyScale).where(TaxonomyScale.id == scale.id))
        await db_session.refresh(objective)

        assert objective.taxonomy_level_id is None
        assert await db_session.get(Objective, objective.id) is not None


class TestFrameworks:
    async def test_defaults(self, framework: Framework) -> None:
        assert framework.profile == FrameworkProfile.CORE
        assert framework.status == FrameworkStatus.DRAFT

    @pytest.mark.parametrize("key", ["Has Spaces", "UPPER", "under_score"])
    async def test_key_format(self, db_session: AsyncSession, key: str) -> None:
        await must_fail(db_session, FrameworkFactory(key=key))

    async def test_key_and_version_unique_among_live_rows(
        self, db_session: AsyncSession, framework: Framework
    ) -> None:
        await must_fail(db_session, FrameworkFactory(key=framework.key))

        await save(db_session, FrameworkFactory(key=framework.key, version_label="2.0"))
        framework.soft_delete()
        await db_session.flush()
        await save(db_session, FrameworkFactory(key=framework.key))

    async def test_activating_supersedes_other_versions(self, db_session: AsyncSession) -> None:
        v1 = FrameworkFactory(key="council", version_label="2019")
        v2 = FrameworkFactory(key="council", version_label="2025")
        unrelated = FrameworkFactory(key="other", status=FrameworkStatus.ACTIVE)
        await save(db_session, v1, v2, unrelated)
        await activate_framework(db_session, v1)

        superseded = await activate_framework(db_session, v2)

        assert superseded == [v1.id]
        await db_session.refresh(v1)
        await db_session.refresh(unrelated)
        assert (v1.status, v2.status, unrelated.status) == (
            FrameworkStatus.SUPERSEDED,
            FrameworkStatus.ACTIVE,
            FrameworkStatus.ACTIVE,
        )

    async def test_deleted_framework_cannot_be_activated(
        self, db_session: AsyncSession, framework: Framework
    ) -> None:
        framework.soft_delete()

        with pytest.raises(InvalidRequestError):
            await activate_framework(db_session, framework)


class TestItems:
    async def test_tree_with_depth(self, db_session: AsyncSession, framework: Framework) -> None:
        root = await add_item(db_session, framework, code="R1", title="Communicator")
        child = await add_item(
            db_session,
            framework,
            code="R1.1",
            title="Listens actively",
            parent=root,
            metadata={"domain": "skill"},
        )
        grandchild = await add_item(
            db_session, framework, code="R1.1.a", title="Summarises", parent=child
        )

        assert (root.depth, child.depth, grandchild.depth) == (0, 1, 2)
        assert grandchild.parent_id == child.id
        assert child.item_metadata == {"domain": "skill"}

    async def test_codes_unique_per_framework(
        self, db_session: AsyncSession, framework: Framework
    ) -> None:
        await add_item(db_session, framework, code="A", title="One")
        other = FrameworkFactory()
        await save(db_session, other)

        with pytest.raises(ConflictError):
            await add_item(db_session, framework, code="A", title="Two")
        await add_item(db_session, other, code="A", title="Same code elsewhere")

    async def test_parent_must_be_in_same_framework(
        self, db_session: AsyncSession, framework: Framework
    ) -> None:
        other = FrameworkFactory()
        await save(db_session, other)
        foreign_parent = await add_item(db_session, other, code="X", title="Foreign")

        with pytest.raises(InvalidRequestError, match="another framework"):
            await add_item(db_session, framework, code="Y", title="Child", parent=foreign_parent)
        # The database enforces it too.
        await must_fail(
            db_session,
            FrameworkItem(
                framework_id=framework.id,
                parent_id=foreign_parent.id,
                depth=1,
                code="Z",
                title="Bypass",
            ),
        )

    async def test_depth_must_match_parent(
        self, db_session: AsyncSession, framework: Framework
    ) -> None:
        await must_fail(
            db_session, FrameworkItem(framework_id=framework.id, depth=1, code="Q", title="Q")
        )

    async def test_blank_code(self, db_session: AsyncSession, framework: Framework) -> None:
        with pytest.raises(InvalidRequestError):
            await add_item(db_session, framework, code="  ", title="No code")

    async def test_deleting_framework_removes_items(
        self, db_session: AsyncSession, framework: Framework
    ) -> None:
        root = await add_item(db_session, framework, code="R", title="Root")
        await add_item(db_session, framework, code="C", title="Child", parent=root)

        await db_session.execute(delete(Framework).where(Framework.id == framework.id))

        assert (await db_session.execute(select(FrameworkItem))).first() is None


class TestCrossReferences:
    async def test_within_and_across_frameworks(
        self, db_session: AsyncSession, framework: Framework
    ) -> None:
        other = FrameworkFactory()
        await save(db_session, other)
        a = await add_item(db_session, framework, code="A", title="A")
        b = await add_item(db_session, framework, code="B", title="B")
        c = await add_item(db_session, other, code="C", title="C")

        await add_cross_ref(db_session, a, b, CrossRefType.PREREQUISITE)
        await add_cross_ref(db_session, a, c, CrossRefType.EQUIVALENT)
        await add_cross_ref(db_session, a, c, CrossRefType.RELATED)  # another type is fine

        with pytest.raises(ConflictError):
            await add_cross_ref(db_session, a, c, CrossRefType.EQUIVALENT)
        with pytest.raises(InvalidRequestError):
            await add_cross_ref(db_session, a, a, CrossRefType.RELATED)
        await must_fail(
            db_session, FrameworkCrossRef(from_item_id=a.id, to_item_id=a.id, type="related")
        )


class TestCrosswalks:
    @pytest.fixture
    async def versions(
        self, db_session: AsyncSession
    ) -> tuple[Crosswalk, dict[str, FrameworkItem]]:
        old = FrameworkFactory(key="council", version_label="2019")
        new = FrameworkFactory(key="council", version_label="2025")
        await save(db_session, old, new)
        items = {
            "old_a": await add_item(db_session, old, code="A", title="A"),
            "old_b": await add_item(db_session, old, code="B", title="B"),
            "new_a": await add_item(db_session, new, code="A", title="A"),
            "new_c": await add_item(db_session, new, code="C", title="C"),
        }
        crosswalk = Crosswalk(from_framework_id=old.id, to_framework_id=new.id)
        await save(db_session, crosswalk)
        return crosswalk, items

    async def test_entries_of_each_type(
        self,
        db_session: AsyncSession,
        versions: tuple[Crosswalk, dict[str, FrameworkItem]],
    ) -> None:
        crosswalk, i = versions

        await add_crosswalk_entry(
            db_session,
            crosswalk,
            CrosswalkEntryType.EQUIVALENT,
            from_item=i["old_a"],
            to_item=i["new_a"],
        )
        await add_crosswalk_entry(
            db_session, crosswalk, CrosswalkEntryType.REMOVED, from_item=i["old_b"]
        )
        await add_crosswalk_entry(db_session, crosswalk, CrosswalkEntryType.NEW, to_item=i["new_c"])
        db_session.expunge_all()

        loaded = (
            await db_session.execute(
                select(Crosswalk)
                .where(Crosswalk.id == crosswalk.id)
                .options(selectinload(Crosswalk.entries))
            )
        ).scalar_one()
        assert sorted(e.type for e in loaded.entries) == ["equivalent", "new", "removed"]

    @pytest.mark.parametrize(
        ("entry_type", "from_key", "to_key", "message"),
        [
            (CrosswalkEntryType.REMOVED, "old_a", "new_a", "no new item"),
            (CrosswalkEntryType.NEW, "old_a", "new_a", "no old item"),
            (CrosswalkEntryType.SPLIT, "old_a", None, "a new item"),
            (CrosswalkEntryType.EQUIVALENT, "new_a", "new_c", "source framework"),
            (CrosswalkEntryType.EQUIVALENT, "old_a", "old_b", "target framework"),
        ],
    )
    async def test_entry_validation(
        self,
        db_session: AsyncSession,
        versions: tuple[Crosswalk, dict[str, FrameworkItem]],
        entry_type: CrosswalkEntryType,
        from_key: str | None,
        to_key: str | None,
        message: str,
    ) -> None:
        crosswalk, i = versions

        with pytest.raises(InvalidRequestError, match=message):
            await add_crosswalk_entry(
                db_session,
                crosswalk,
                entry_type,
                from_item=i[from_key] if from_key else None,
                to_item=i[to_key] if to_key else None,
            )

    async def test_database_checks(
        self,
        db_session: AsyncSession,
        versions: tuple[Crosswalk, dict[str, FrameworkItem]],
    ) -> None:
        from app.models import CrosswalkEntry

        crosswalk, i = versions

        await must_fail(
            db_session,
            CrosswalkEntry(
                crosswalk_id=crosswalk.id,
                type="removed",
                from_item_id=i["old_a"].id,
                to_item_id=i["new_a"].id,
            ),
        )
        await must_fail(
            db_session,
            Crosswalk(
                from_framework_id=crosswalk.from_framework_id,
                to_framework_id=crosswalk.from_framework_id,
            ),
        )


async def test_demo_pack_fits_the_models(db_session: AsyncSession) -> None:
    """Load the shipped demo pack into the models, as the phase 1 importer will."""
    pack = json.loads(DEMO_PACK.read_text(encoding="utf-8"))
    meta = pack["metadata"]
    framework = Framework(
        key=meta["key"],
        name=meta["name"],
        version_label=meta["version"],
        publisher=meta["publisher"],
        licence_note=meta.get("licence", ""),
        description=meta.get("description", ""),
        profile=meta.get("profile", "core"),
    )
    await save(db_session, framework)

    by_code: dict[str, FrameworkItem] = {}
    pending = list(pack["items"])
    while pending:  # parents before children
        ready = [i for i in pending if not i.get("parent_code") or i["parent_code"] in by_code]
        assert ready, "pack items form a cycle or reference a missing parent"
        for raw in ready:
            by_code[raw["code"]] = await add_item(
                db_session,
                framework,
                code=raw["code"],
                title=raw["title"],
                description=raw.get("description", ""),
                parent=by_code.get(raw.get("parent_code") or ""),
                position=raw.get("order", 0),
                metadata=raw.get("metadata"),
            )
            pending.remove(raw)
    for ref in pack.get("cross_references", []):
        await add_cross_ref(
            db_session,
            by_code[ref["from_code"]],
            by_code[ref["to_code"]],
            CrossRefType(ref["type"]),
        )
    for raw_scale in pack.get("taxonomy_scales", []):
        scale = TaxonomyScale(
            key=raw_scale["key"],
            name=raw_scale["name"],
            description=raw_scale.get("description", ""),
        )
        await save(db_session, scale)
        db_session.add_all(
            TaxonomyLevel(
                scale_id=scale.id,
                position=lvl["order"],
                name=lvl["name"],
                description=lvl.get("description", ""),
                verbs=lvl.get("verbs", []),
            )
            for lvl in raw_scale["levels"]
        )
    await db_session.flush()

    assert len(by_code) == len(pack["items"])
    assert max(item.depth for item in by_code.values()) >= 1
    scales = (await db_session.execute(select(TaxonomyScale.key))).scalars().all()
    assert set(scales) == {s["key"] for s in pack["taxonomy_scales"]}
