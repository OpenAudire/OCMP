"""Tests for gold sets (ADR 048): the Excel template, reading it, saving it, and the demo set."""

import io
import json
from pathlib import Path
from typing import Any

import pytest
from openpyxl import Workbook, load_workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import GoldCase, GoldLink
from app.models.mapping import DepthMatch
from app.services import eval_gold
from app.services.authorization import ConflictError, InvalidRequestError
from tests.mapping_helpers import Library, make_library

HEADERS = list(eval_gold.HEADERS)
DATA = Path(__file__).parent.parent / "app" / "demo" / "data"


def workbook(rows: list[list[Any]], headers: list[str] | None = None) -> bytes:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.title = "Gold set"
    sheet.append(headers or HEADERS)
    for row in rows:
        sheet.append(row)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


@pytest.fixture
async def library(db_session: AsyncSession) -> Library:
    return await make_library(db_session)


class TestReading:
    def test_groups_rows_into_objectives_by_wording_ignoring_case_and_spacing(self) -> None:
        parsed = eval_gold.read_workbook(
            workbook(
                [
                    ["Describe the heart.", "HRT1", 4, "matches"],
                    ["  describe   the HEART. ", "COM1", 1, None],
                    ["Be kind.", "ETH1", 5, "below"],
                ]
            )
        )

        assert parsed.problems == []
        assert [c.text for c in parsed.cases] == ["Describe the heart.", "Be kind."]
        assert [(r.code, r.coverage, r.depth) for r in parsed.cases[0].rows] == [
            ("HRT1", 4, DepthMatch.MATCHES),
            ("COM1", 1, None),
        ]

    def test_an_objective_with_no_code_maps_to_nothing(self) -> None:
        parsed = eval_gold.read_workbook(workbook([["List the bones.", None, None, None]]))

        assert parsed.problems == [] and parsed.empty_cases == 1 and parsed.links == 0

    def test_coverage_zero_is_a_row_and_whole_numbers_given_as_text_are_accepted(self) -> None:
        parsed = eval_gold.read_workbook(
            workbook([["Describe the heart.", "HRT1", 0, None], ["Be kind.", "ETH1", "3", None]])
        )

        assert parsed.problems == []
        assert parsed.cases[0].rows[0].coverage == 0 and parsed.cases[1].rows[0].coverage == 3

    def test_depth_may_be_written_with_a_space_or_in_capitals(self) -> None:
        parsed = eval_gold.read_workbook(
            workbook([["A.", "X1", 2, "Not applicable"], ["B.", "X1", 2, "ABOVE"]])
        )

        assert [c.rows[0].depth for c in parsed.cases] == [
            DepthMatch.NOT_APPLICABLE,
            DepthMatch.ABOVE,
        ]

    def test_blank_rows_are_skipped(self) -> None:
        parsed = eval_gold.read_workbook(
            workbook([["A.", "X1", 2, None], [None, None, None, None], ["B.", "X1", 2, None]])
        )

        assert len(parsed.cases) == 2 and parsed.problems == []

    @pytest.mark.parametrize(
        ("row", "message"),
        [
            ([None, "X1", 3, None], "objective text is empty"),
            (["A.", "X1", 6, None], "whole number 0 to 5"),
            (["A.", "X1", 2.5, None], "whole number 0 to 5"),
            (["A.", "X1", "many", None], "whole number 0 to 5"),
            (["A.", "X1", None, None], "whole number 0 to 5"),
            (["A.", "X1", 3, "deeper"], "depth must be"),
            (["A.", None, 3, None], "needs a framework item code"),
            (["A.", None, None, "below"], "needs a framework item code"),
            (["x" * 2001, "X1", 3, None], "too long"),
        ],
    )
    def test_each_problem_is_reported_with_its_row_number(
        self, row: list[Any], message: str
    ) -> None:
        parsed = eval_gold.read_workbook(workbook([["Fine.", "X1", 1, None], row]))

        assert [p.row for p in parsed.problems] == [3]
        assert message in parsed.problems[0].message

    def test_a_repeated_objective_and_code_is_a_problem(self) -> None:
        parsed = eval_gold.read_workbook(workbook([["A.", "X1", 1, None], ["a.", "x1", 2, None]]))

        assert [p.row for p in parsed.problems] == [3]

    def test_every_problem_is_listed_not_only_the_first(self) -> None:
        parsed = eval_gold.read_workbook(
            workbook([["A.", "X1", 9, None], ["B.", "X1", "no", None], ["C.", "X1", 1, "?"]])
        )

        assert [p.row for p in parsed.problems] == [2, 3, 4]

    def test_headings_are_found_by_name_not_position(self) -> None:
        parsed = eval_gold.read_workbook(
            workbook(
                [["note", 4, "A.", "below", "X1"]],
                headers=[
                    "Notes",
                    "Coverage (0-5)",
                    "Objective text",
                    "Depth",
                    "Framework item code",
                ],
            )
        )

        assert parsed.problems == []
        assert parsed.cases[0].text == "A."
        assert (parsed.cases[0].rows[0].code, parsed.cases[0].rows[0].coverage) == ("X1", 4)

    def test_a_file_that_is_not_a_workbook_is_a_problem_not_a_crash(self) -> None:
        parsed = eval_gold.read_workbook(b"this is not excel")

        assert len(parsed.problems) == 1 and "not an Excel" in parsed.problems[0].message

    def test_a_workbook_without_the_headings_is_refused(self) -> None:
        parsed = eval_gold.read_workbook(workbook([["A.", "X1", 1, None]], headers=["a", "b"]))

        assert "headings must be" in parsed.problems[0].message

    def test_a_workbook_with_no_objectives_is_refused(self) -> None:
        parsed = eval_gold.read_workbook(workbook([]))

        assert "no objectives" in parsed.problems[0].message

    def test_a_file_over_the_size_limit_is_refused_before_it_is_read(self) -> None:
        parsed = eval_gold.read_workbook(b"0" * (eval_gold.MAX_FILE_BYTES + 1))

        assert "larger than 5 MB" in parsed.problems[0].message


class TestTemplate:
    async def test_the_template_has_headings_instructions_and_the_item_codes(
        self, db_session: AsyncSession, library: Library
    ) -> None:
        content = await eval_gold.build_template(db_session, library.framework)

        book = load_workbook(io.BytesIO(content))
        assert book.sheetnames == ["Gold set", "Instructions", "Framework items"]
        assert [c.value for c in book["Gold set"][1]] == HEADERS
        codes = [row[0].value for row in book["Framework items"].iter_rows(min_row=2)]
        assert codes == ["COM1", "ETH1", "HRT1", "HYG1"]
        assert book["Gold set"].max_row == 1  # no example rows to import by mistake

    async def test_dropdowns_limit_coverage_depth_and_codes(
        self, db_session: AsyncSession, library: Library
    ) -> None:
        book = load_workbook(
            io.BytesIO(await eval_gold.build_template(db_session, library.framework))
        )

        rules = {str(v.sqref): v for v in book["Gold set"].data_validations.dataValidation}
        assert rules["C2:C5000"].type == "whole" and rules["C2:C5000"].formula2 == "5"
        assert rules["D2:D5000"].formula1 == '"below,matches,above,not_applicable"'
        assert "'Framework items'!$A$2:$A$5" in rules["B2:B5000"].formula1

    async def test_the_template_without_a_framework_has_no_code_list(
        self, db_session: AsyncSession
    ) -> None:
        book = load_workbook(io.BytesIO(await eval_gold.build_template(db_session, None)))

        assert "Framework items" not in book.sheetnames

    async def test_an_untouched_template_cannot_be_imported(
        self, db_session: AsyncSession, library: Library
    ) -> None:
        parsed = await eval_gold.preview(
            db_session, library.framework, await eval_gold.build_template(db_session, None)
        )

        assert parsed.problems and not parsed.cases


class TestSaving:
    async def test_checks_codes_against_the_framework_ignoring_case(
        self, db_session: AsyncSession, library: Library
    ) -> None:
        parsed = await eval_gold.preview(
            db_session,
            library.framework,
            workbook([["A.", "hrt1", 3, None], ["B.", "NOPE", 3, None]]),
        )

        assert [(p.row, "NOPE" in p.message) for p in parsed.problems] == [(3, True)]
        assert parsed.cases[0].rows[0].code == "HRT1"

    async def test_saves_objectives_and_mappings(
        self, db_session: AsyncSession, library: Library
    ) -> None:
        parsed = await eval_gold.preview(
            db_session,
            library.framework,
            workbook(
                [
                    ["Describe the heart.", "HRT1", 4, "matches"],
                    ["Be kind.", "ETH1", 0, None],
                    ["List the bones.", None, None, None],
                ]
            ),
        )

        gold = await eval_gold.save_gold_set(
            db_session,
            actor_id=None,
            name="  First   set ",
            description="",
            framework=library.framework,
            parsed=parsed,
        )

        assert gold.name == "First set" and gold.is_demo is False
        cases = list(await db_session.scalars(select(GoldCase).order_by(GoldCase.position)))
        assert [c.objective_text for c in cases] == [
            "Describe the heart.",
            "Be kind.",
            "List the bones.",
        ]
        links = list(await db_session.scalars(select(GoldLink)))
        assert sorted((link.item_code, link.coverage) for link in links) == [
            ("ETH1", 0),
            ("HRT1", 4),
        ]

    async def test_nothing_is_saved_when_there_are_problems(
        self, db_session: AsyncSession, library: Library
    ) -> None:
        parsed = await eval_gold.preview(
            db_session, library.framework, workbook([["A.", "HRT1", 9, None]])
        )

        with pytest.raises(eval_gold.GoldSetInvalid) as caught:
            await eval_gold.save_gold_set(
                db_session,
                actor_id=None,
                name="Bad",
                description="",
                framework=library.framework,
                parsed=parsed,
            )

        assert caught.value.problems[0].row == 2
        assert list(await db_session.scalars(select(GoldCase))) == []

    async def test_a_name_is_needed_and_must_be_new(
        self, db_session: AsyncSession, library: Library
    ) -> None:
        parsed = await eval_gold.preview(
            db_session, library.framework, workbook([["A.", "HRT1", 3, None]])
        )
        args: dict[str, Any] = {
            "actor_id": None,
            "description": "",
            "framework": library.framework,
            "parsed": parsed,
        }

        with pytest.raises(InvalidRequestError):
            await eval_gold.save_gold_set(db_session, name="  ", **args)
        await eval_gold.save_gold_set(db_session, name="Once", **args)
        with pytest.raises(ConflictError):
            await eval_gold.save_gold_set(db_session, name="Once", **args)

    async def test_an_export_can_be_imported_again_unchanged(
        self, db_session: AsyncSession, library: Library
    ) -> None:
        original = workbook(
            [
                ["Describe the heart.", "HRT1", 4, "matches"],
                ["Describe the heart.", "COM1", 2, "below"],
                ["List the bones.", None, None, None],
            ]
        )
        parsed = await eval_gold.preview(db_session, library.framework, original)
        gold = await eval_gold.save_gold_set(
            db_session,
            actor_id=None,
            name="Round trip",
            description="",
            framework=library.framework,
            parsed=parsed,
        )

        again = eval_gold.read_workbook(await eval_gold.export_gold_set(db_session, gold))

        assert again.problems == []
        shape = lambda p: [  # noqa: E731
            (c.text, sorted((r.code, r.coverage, r.depth) for r in c.rows)) for c in p.cases
        ]
        assert shape(again) == shape(parsed)


class TestDemoGoldSet:
    """The shipped fictional set must describe the shipped demo data (a drift would silently
    make every demo evaluation report 'not found')."""

    def test_covers_every_demo_objective_exactly_once(self) -> None:
        demo = json.loads((DATA / "bsc-health-sciences-demo.json").read_text(encoding="utf-8"))
        # The 2026 version only: the 2027 draft ("next_year") adds an objective of its own.
        texts = _objective_texts([demo["programme"], demo["modules"]])
        gold = json.loads((DATA / "gold-set-demo.json").read_text(encoding="utf-8"))

        wording = [eval_gold.normal(c["objective"]) for c in gold["cases"]]

        assert len(wording) == len(set(wording))
        assert set(wording) == {eval_gold.normal(t) for t in texts}

    def test_uses_only_codes_of_the_demo_framework_and_valid_values(self) -> None:
        framework = json.loads((DATA / "demo-graduate-competencies.json").read_text("utf-8"))
        codes = {item["code"] for item in framework["items"]}
        gold = json.loads((DATA / "gold-set-demo.json").read_text(encoding="utf-8"))

        parsed = eval_gold.read_json(gold)

        assert parsed.problems == []
        used = {r.code for c in parsed.cases for r in c.rows}
        assert used and used <= codes
        assert all(0 <= r.coverage <= 5 for c in parsed.cases for r in c.rows)
        assert any(not c.rows for c in parsed.cases), "some objectives must map to nothing"

    def test_says_plainly_that_it_is_fictional(self) -> None:
        gold = json.loads((DATA / "gold-set-demo.json").read_text(encoding="utf-8"))

        assert "FICTIONAL" in gold["_comment"] and "(fictional)" in gold["name"]


def _objective_texts(node: Any) -> list[str]:
    """Every objective text in the demo file, wherever the loader keeps them."""
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key in {"outcomes", "objectives"} and isinstance(value, list):
                found.extend(v["text"] for v in value if isinstance(v, dict) and "text" in v)
            else:
                found.extend(_objective_texts(value))
    elif isinstance(node, list):
        for value in node:
            found.extend(_objective_texts(value))
    return [t for t in found if t]
