"""Tests for pack format version 2 (crosswalks, tag lists, other-framework references)
and the structure-only templates (ADR 036)."""

import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CrosswalkEntry, FrameworkCrossRef, TagList, TagValue
from app.models.framework import CrossRefType, CrosswalkEntryType
from app.models.tagging import TaggableType, TagListKind
from app.services.authorization import InvalidRequestError
from app.services.packs import FORMAT_VERSION, check_pack, import_pack, load_pack_file, parse_pack

REPO = Path(__file__).resolve().parents[2]
TEMPLATES = REPO / "packs" / "templates"
BUNDLED_TEMPLATES = REPO / "backend" / "app" / "pack_templates"


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


def pack_v2(**overrides: Any) -> dict[str, Any]:
    return pack(format_version=2, **overrides)


def second_version(**overrides: Any) -> dict[str, Any]:
    data = pack_v2(**overrides)
    data["metadata"] = {**data["metadata"], "version": "2"}
    return data


def other_framework() -> dict[str, Any]:
    data = pack()
    data["metadata"] = {**data["metadata"], "key": "other-pack"}
    return data


class TestFormatVersions:
    def test_old_packs_without_a_format_version_stay_valid(self) -> None:
        assert parse_pack(pack()).format_version == 1

    @pytest.mark.parametrize(
        "extra",
        [
            {"tag_lists": [{"key": "t", "name": "T", "values": [{"label": "x"}]}]},
            {
                "crosswalks": [
                    {"from_version": "0", "entries": [{"type": "removed", "from_code": "A"}]}
                ]
            },
            {
                "cross_references": [
                    {"from_code": "A", "to_code": "Z", "type": "related", "to_framework": "o"}
                ]
            },
        ],
        ids=["tag-lists", "crosswalks", "other-framework"],
    )
    def test_new_sections_need_format_two(self, extra: dict[str, Any]) -> None:
        with pytest.raises(InvalidRequestError, match="format_version"):
            parse_pack(pack(**extra))

    def test_a_newer_format_than_this_installation_reads_is_refused(self) -> None:
        with pytest.raises(InvalidRequestError, match="up to version 2"):
            parse_pack(pack(format_version=3))

    def test_all_problems_are_listed_with_paths(self) -> None:
        data = pack(
            items=[
                {"code": "A", "title": "A"},
                {"code": "A", "title": "B", "parent_code": "Q"},
                {"code": "C", "title": ""},
            ]
        )

        parsed, problems = check_pack(data)
        assert parsed is None
        assert {p.path for p in problems} == {"items[2].title"}

        data["items"][2]["title"] = "C"
        _, problems = check_pack(data)
        assert {p.path for p in problems} == {"items[1].code", "items[1].parent_code"}

    def test_a_pack_that_is_not_an_object(self) -> None:
        _, problems = check_pack([1, 2])
        assert "JSON object" in problems[0].message

    @pytest.mark.parametrize(
        ("extra", "message"),
        [
            (
                {
                    "crosswalks": [
                        {"from_version": "0", "entries": [{"type": "equivalent", "from_code": "A"}]}
                    ]
                },
                "needs",
            ),
            (
                {
                    "crosswalks": [
                        {"from_version": "1", "entries": [{"type": "new", "to_code": "A"}]}
                    ]
                },
                "earlier version",
            ),
            (
                {
                    "crosswalks": [
                        {"from_version": "0", "entries": [{"type": "new", "to_code": "Z"}]}
                    ]
                },
                "not an item of this pack",
            ),
            (
                {
                    "tag_lists": [
                        {"key": "t", "name": "T", "values": [{"label": "x"}, {"label": "x"}]}
                    ]
                },
                "repeats",
            ),
            (
                {"cross_references": [{"from_code": "A", "to_code": "A", "type": "related"}]},
                "itself",
            ),
            (
                {
                    "cross_references": [
                        {"from_code": "A", "to_code": "A.1", "type": "related", "to_version": "1"}
                    ]
                },
                "to_framework",
            ),
        ],
        ids=["entry-shape", "same-version", "unknown-target", "tag-repeat", "self-ref", "version"],
    )
    def test_new_section_problems(self, extra: dict[str, Any], message: str) -> None:
        with pytest.raises(InvalidRequestError, match=message):
            parse_pack(pack_v2(**extra))


class TestImportFormatTwo:
    async def test_tag_lists_are_created_and_reused(self, db_session: AsyncSession) -> None:
        lists: list[dict[str, Any]] = [
            {
                "key": "themes",
                "name": "Themes",
                "kind": "theme",
                "entity_types": ["module"],
                "values": [
                    {"label": "Ethics", "code": "E", "order": 2},
                    {"label": "Safety", "order": 1},
                ],
            }
        ]
        first = await import_pack(db_session, parse_pack(pack_v2(tag_lists=lists)))
        lists[0]["values"].append({"label": "Teamwork"})
        second = await import_pack(db_session, parse_pack(second_version(tag_lists=lists)))

        assert (first.summary.tag_lists_created, first.summary.tag_values_added) == (1, 2)
        assert (second.summary.tag_lists_created, second.summary.tag_values_added) == (0, 1)
        stored = await db_session.scalars(
            select(TagValue)
            .join(TagList)
            .where(TagList.key == "themes")
            .order_by(TagValue.position)
        )
        assert [v.label for v in stored] == ["Safety", "Ethics", "Teamwork"]

    async def test_crosswalk_from_an_earlier_version(self, db_session: AsyncSession) -> None:
        await import_pack(db_session, parse_pack(pack()))
        crosswalk = {
            "from_version": "1",
            "notes": "2 replaces 1",
            "entries": [
                {"type": "equivalent", "from_code": "A", "to_code": "A"},
                {"type": "removed", "from_code": "A.1"},
                {"type": "new", "to_code": "A.1"},
            ],
        }

        result = await import_pack(db_session, parse_pack(second_version(crosswalks=[crosswalk])))

        assert (result.summary.crosswalks, result.summary.crosswalk_entries) == (1, 3)
        entries = await db_session.scalars(select(CrosswalkEntry))
        assert {e.type.value for e in entries} == {"equivalent", "removed", "new"}

    async def test_crosswalk_from_a_missing_version_is_refused(
        self, db_session: AsyncSession
    ) -> None:
        crosswalk = {"from_version": "9", "entries": [{"type": "new", "to_code": "A"}]}

        with pytest.raises(InvalidRequestError, match="not imported"):
            await import_pack(db_session, parse_pack(second_version(crosswalks=[crosswalk])))

    async def test_crosswalk_from_an_unknown_old_item_is_refused(
        self, db_session: AsyncSession
    ) -> None:
        await import_pack(db_session, parse_pack(pack()))
        crosswalk = {"from_version": "1", "entries": [{"type": "removed", "from_code": "NOPE"}]}

        with pytest.raises(InvalidRequestError, match="NOPE"):
            await import_pack(db_session, parse_pack(second_version(crosswalks=[crosswalk])))

    async def test_references_to_another_framework(self, db_session: AsyncSession) -> None:
        await import_pack(db_session, parse_pack(other_framework()))
        ref = {"from_code": "A", "to_code": "A.1", "type": "related", "to_framework": "other-pack"}

        result = await import_pack(db_session, parse_pack(pack_v2(cross_references=[ref])))

        assert result.summary.external_references == 1
        link = await db_session.scalar(select(FrameworkCrossRef))
        assert link is not None
        assert link.from_item_id == result.items["A"].id
        assert link.to_item_id != result.items["A.1"].id  # the other framework's A.1

    async def test_references_to_a_missing_framework_or_item_are_refused(
        self, db_session: AsyncSession
    ) -> None:
        ref = {"from_code": "A", "to_code": "A.1", "type": "related", "to_framework": "nope"}
        with pytest.raises(InvalidRequestError, match="not imported yet"):
            await import_pack(db_session, parse_pack(pack_v2(cross_references=[ref])))

        await import_pack(db_session, parse_pack(other_framework()))
        ref = {"from_code": "A", "to_code": "ZZ", "type": "related", "to_framework": "other-pack"}
        with pytest.raises(InvalidRequestError, match="ZZ"):
            await import_pack(db_session, parse_pack(pack_v2(cross_references=[ref])))

    async def test_a_template_cannot_be_imported(self, db_session: AsyncSession) -> None:
        data = pack()
        data["metadata"] = {**data["metadata"], "template": True}

        with pytest.raises(InvalidRequestError, match="template"):
            await import_pack(db_session, parse_pack(data))

    async def test_large_pack_imports_in_levels(self, db_session: AsyncSession) -> None:
        items = [{"code": "R", "title": "R"}] + [
            {"code": f"C{n}", "title": f"C{n}", "parent_code": "R", "order": n} for n in range(500)
        ]

        result = await import_pack(db_session, parse_pack(pack(items=items)))

        assert result.summary.items == 501
        assert result.items["C499"].depth == 1


class TestTemplates:
    @pytest.mark.parametrize("path", sorted(TEMPLATES.glob("*.json")), ids=lambda p: p.stem)
    def test_templates_are_valid_blank_structures(self, path: Path) -> None:
        loaded = load_pack_file(path)

        assert loaded.metadata.template
        assert all(item.metadata.get("placeholder") for item in loaded.items)
        assert path.read_text(encoding="utf-8") == (BUNDLED_TEMPLATES / path.name).read_text(
            encoding="utf-8"
        )

    def test_the_four_templates_ship(self) -> None:
        names = {p.stem for p in TEMPLATES.glob("*.json")}
        assert names == {
            "hpcsa-core-competencies",
            "nqf-level-descriptors",
            "graduate-attributes",
            "mesh-subset",
        }
        assert {p.stem for p in BUNDLED_TEMPLATES.glob("*.json")} == names

    def test_the_nqf_template_has_ten_levels(self) -> None:
        loaded = load_pack_file(TEMPLATES / "nqf-level-descriptors.json")
        assert [i.metadata["nqf_level"] for i in loaded.items] == list(range(1, 11))


class TestSchemaFile:
    def test_schema_describes_the_format_two_sections_and_enums(self) -> None:
        schema = json.loads(
            (REPO / "packs" / "schema" / "framework-pack.schema.json").read_text("utf-8")
        )
        props = schema["properties"]

        assert {"format_version", "crosswalks", "tag_lists"} <= set(props)
        assert props["metadata"]["properties"]["template"]["type"] == "boolean"
        ref = props["cross_references"]["items"]["properties"]
        assert set(ref["type"]["enum"]) == {t.value for t in CrossRefType}
        assert {"to_framework", "to_version"} <= set(ref)
        entry = props["crosswalks"]["items"]["properties"]["entries"]["items"]["properties"]
        assert set(entry["type"]["enum"]) == {t.value for t in CrosswalkEntryType}
        tags = props["tag_lists"]["items"]["properties"]
        assert set(tags["kind"]["enum"]) == {k.value for k in TagListKind}
        assert set(tags["entity_types"]["items"]["enum"]) == {t.value for t in TaggableType}
        assert props["format_version"]["maximum"] == FORMAT_VERSION
