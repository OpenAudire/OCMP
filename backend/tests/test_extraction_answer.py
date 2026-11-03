"""Tests for checking the model's answer to the study-guide extraction prompt (ADR 047)."""

import json

import pytest

from app.ai.extraction_answer import MAX_PER_PIECE, QUOTE_MAX_CHARS, parse_extraction
from app.ai.objective_answers import InvalidAnswer
from app.models.curriculum import ObjectiveDomain

GUIDE = (
    "By the end of this module you will be able to:\n"
    "Describe the structure of the heart and the cardiac cycle.\n"
    "Measure blood pressure on 2 occasions."
)


def item(**changes: object) -> dict[str, object]:
    return {
        "text": "Describe the structure of the heart and the cardiac cycle.",
        "domain": "knowledge",
        "source_quote": "Describe the structure of the heart and the cardiac cycle.",
        **changes,
    }


def answer(*items: dict[str, object]) -> str:
    return json.dumps({"objectives": list(items)})


def problems_of(text: str) -> list[str]:
    with pytest.raises(InvalidAnswer) as raised:
        parse_extraction(text, guide_text=GUIDE)
    return raised.value.problems


class TestValid:
    def test_an_objective_with_its_quote(self) -> None:
        (found,) = parse_extraction(answer(item()), guide_text=GUIDE)
        assert found.text.startswith("Describe the structure")
        assert found.domain is ObjectiveDomain.KNOWLEDGE
        assert found.source_quote.endswith("cardiac cycle.")

    def test_none_found_is_a_valid_answer(self) -> None:
        assert parse_extraction(answer(), guide_text=GUIDE) == []

    def test_spacing_and_case_of_the_quote_do_not_matter(self) -> None:
        quote = "describe  the structure\nof the HEART"
        assert parse_extraction(answer(item(source_quote=quote)), guide_text=GUIDE)

    def test_a_code_fence_is_tolerated_and_the_domain_may_be_null(self) -> None:
        text = "```json\n" + answer(item(domain=None)) + "\n```"
        assert parse_extraction(text, guide_text=GUIDE)[0].domain is None

    def test_the_same_wording_twice_is_kept_once(self) -> None:
        found = parse_extraction(
            answer(item(), item(text="describe the structure of the heart and the cardiac cycle.")),
            guide_text=GUIDE,
        )
        assert len(found) == 1

    def test_a_number_that_is_in_the_quote_may_be_used(self) -> None:
        text = answer(
            item(
                text="Measure blood pressure on 2 occasions.",
                source_quote="Measure blood pressure on 2 occasions.",
            )
        )
        assert parse_extraction(text, guide_text=GUIDE)


class TestInvalid:
    def test_a_quote_that_is_not_in_the_guide_is_refused(self) -> None:
        text = answer(item(source_quote="Name every bone in the human body."))
        assert problems_of(text) == [
            "objective 1: the source_quote is not words of the study guide"
        ]

    def test_a_made_up_number_is_refused(self) -> None:
        text = answer(item(text="Describe the heart in 5 minutes."))
        assert problems_of(text) == [
            "objective 1: the text has a number that is not in the source_quote"
        ]

    def test_wording_and_quote_are_required(self) -> None:
        assert problems_of(answer(item(text=" "))) == ['objective 1: "text" is missing']
        assert problems_of(answer(item(source_quote=""))) == [
            'objective 1: "source_quote" is missing'
        ]

    def test_a_quote_that_is_too_long_is_refused(self) -> None:
        long = "Describe " + "the " * QUOTE_MAX_CHARS
        assert problems_of(answer(item(source_quote=long)))[0].startswith(
            "objective 1: the source_quote is longer than"
        )

    def test_an_unknown_domain_is_refused(self) -> None:
        assert problems_of(answer(item(domain="feeling"))) == [
            "objective 1: the domain is not knowledge, skill, attitude or null"
        ]

    def test_too_many_objectives_are_refused(self) -> None:
        text = answer(*[item(text=f"Objective {n}") for n in range(MAX_PER_PIECE + 1)])
        assert problems_of(text) == [f"there are more than {MAX_PER_PIECE} objectives"]

    @pytest.mark.parametrize(
        ("text", "problem"),
        [
            ("not json", "the answer is not JSON"),
            ("[]", 'the answer has no "objectives" list'),
            ('{"objectives": "x"}', 'the answer has no "objectives" list'),
            (json.dumps({"objectives": ["x"]}), "objective 1 is not an object"),
        ],
    )
    def test_the_shape_is_checked(self, text: str, problem: str) -> None:
        assert problems_of(text) == [problem]

    def test_the_models_words_are_never_in_a_problem(self) -> None:
        text = answer(item(source_quote="secret=hunter2 is not in the guide"))
        assert "hunter2" not in " ".join(problems_of(text))
