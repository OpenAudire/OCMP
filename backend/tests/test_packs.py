"""Tests for framework pack validation and import."""

import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FrameworkCrossRef, TaxonomyLevel, TaxonomyScale
from app.services.authorization import ConflictError, InvalidRequestError
from app.services.packs import import_pack, load_pack_file, parse_pack

REPO = Path(__file__).resolve().parents[2]
DEMO_PACK = REPO / "packs" / "demo" / "demo-graduate-competencies.json"
BUNDLED_PACK = REPO / "backend" / "app" / "demo" / "data" / "demo-graduate-competencies.json"


def pack(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "metadata": {"key": "test-pack", "name": "Test", "version": "1", "publisher": "Tests"},
        "items": [
            {"code": "A", "title": "A"},
            {"code": "A.1", "title": "A.1", "parent_code": "A"},
        ],
    }
    data.update(overrides)
    return data


class TestValidation:
    def test_shipped_demo_pack_matches_the_bundled_copy(self) -> None:
        """The demo loader's copy must not drift from the published example pack."""
        assert DEMO_PACK.read_text(encoding="utf-8") == BUNDLED_PACK.read_text(encoding="utf-8")

    def test_demo_pack_has_eight_items_in_two_levels(self) -> None:
        demo = load_pack_file(DEMO_PACK)

        assert len(demo.items) == 8
        roots = [i for i in demo.items if i.parent_code is None]
        children = [i for i in demo.items if i.parent_code is not None]
        assert len(roots) == 2
        assert {c.parent_code for c in children} == {r.code for r in roots}
        assert {s.key for s in demo.taxonomy_scales} == {"bloom-revised", "miller"}

    @pytest.mark.parametrize(
        ("overrides", "message"),
        [
            ({"items": [{"code": "A", "title": "A"}, {"code": "A", "title": "B"}]}, "unique"),
            ({"items": [{"code": "A", "title": "A", "parent_code": "Z"}]}, "unknown parent"),
            (
                {
                    "items": [
                        {"code": "A", "title": "A", "parent_code": "B"},
                        {"code": "B", "title": "B", "parent_code": "A"},
                    ]
                },
                "cycle",
            ),
            (
                {"cross_references": [{"from_code": "A", "to_code": "Z", "type": "related"}]},
                "Cross-reference",
            ),
            (
                {
                    "taxonomy_scales": [
                        {
                            "key": "s",
                            "name": "S",
                            "levels": [{"order": 1, "name": "X"}, {"order": 1, "name": "Y"}],
                        }
                    ]
                },
                "repeats",
            ),
            (
                {"metadata": {"key": "Bad Key", "name": "N", "version": "1", "publisher": "P"}},
                "key",
            ),
            ({"items": []}, "items"),
        ],
        ids=[
            "duplicate-code",
            "unknown-parent",
            "cycle",
            "bad-cross-ref",
            "scale-levels",
            "bad-key",
            "no-items",
        ],
    )
    def test_invalid_packs(self, overrides: dict[str, Any], message: str) -> None:
        with pytest.raises(InvalidRequestError, match=message):
            parse_pack(pack(**overrides))


class TestImport:
    async def test_imports_tree_cross_refs_and_scales(self, db_session: AsyncSession) -> None:
        result = await import_pack(db_session, load_pack_file(DEMO_PACK))

        assert result.framework.key == "demo-graduate-competencies"
        assert len(result.items) == 8
        assert result.items["DGC-1.2"].parent_id == result.items["DGC-1"].id
        assert result.items["DGC-1.2"].depth == 1
        assert await db_session.scalar(select(func.count()).select_from(FrameworkCrossRef)) == 1
        levels = await db_session.scalar(
            select(func.count())
            .select_from(TaxonomyLevel)
            .join(TaxonomyScale)
            .where(TaxonomyScale.key == "bloom-revised")
        )
        assert levels == 6

    async def test_same_version_twice_is_refused(self, db_session: AsyncSession) -> None:
        await import_pack(db_session, parse_pack(pack()))

        with pytest.raises(ConflictError, match="already imported"):
            await import_pack(db_session, parse_pack(pack()))

    async def test_existing_scales_are_reused(self, db_session: AsyncSession) -> None:
        scales = [{"key": "s", "name": "S", "levels": [{"order": 0, "name": "L"}]}]
        await import_pack(db_session, parse_pack(pack(taxonomy_scales=scales)))
        second = pack(taxonomy_scales=scales)
        second["metadata"] = {**second["metadata"], "version": "2"}

        await import_pack(db_session, parse_pack(second))

        assert await db_session.scalar(select(func.count()).select_from(TaxonomyScale)) == 1

    async def test_items_in_any_order(self, db_session: AsyncSession) -> None:
        reversed_items = list(reversed(json.loads(json.dumps(pack()["items"]))))

        result = await import_pack(db_session, parse_pack(pack(items=reversed_items)))

        assert result.items["A.1"].parent_id == result.items["A"].id
