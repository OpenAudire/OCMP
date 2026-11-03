"""Tests for checking the answers to the rewrite and classification prompts (ADR 046)."""

import json
from decimal import Decimal

import pytest

from app.ai.objective_answers import (
    REWRITE_MAX_CHARS,
    InvalidAnswer,
    parse_classification,
    parse_rewrite,
)
from app.models.curriculum import ObjectiveDomain

ORIGINAL = "Understand the cardiac cycle in 2 phases."


def rewrite_answer(**changes: object) -> str:
    return json.dumps(
        {
            "text": "Describe the 2 phases of the cardiac cycle.",
            "rationale": "Replaced a vague verb with a measurable one.",
            **changes,
        }
    )


def problems_of_rewrite(text: str) -> list[str]:
    with pytest.raises(InvalidAnswer) as raised:
        parse_rewrite(text, original=ORIGINAL)
    return raised.value.problems


class TestRewrite:
    def test_a_valid_rewrite(self) -> None:
        result = parse_rewrite(rewrite_answer(), original=ORIGINAL)
        assert result.text == "Describe the 2 phases of the cardiac cycle."
        assert result.rationale == "Replaced a vague verb with a measurable one."
        assert result.unchanged is False

    def test_a_code_fence_and_spacing_are_tolerated(self) -> None:
        text = "```json\n" + rewrite_answer(text="  Describe   the\n2 phases. ") + "\n```"
        assert parse_rewrite(text, original=ORIGINAL).text == "Describe the 2 phases."

    def test_wording_returned_as_it_was_is_marked_unchanged(self) -> None:
        text = rewrite_answer(text="understand the cardiac cycle in 2 phases.")
        assert parse_rewrite(text, original=ORIGINAL).unchanged is True

    def test_a_number_of_the_original_may_be_kept(self) -> None:
        assert parse_rewrite(rewrite_answer(text="Name 2 phases."), original=ORIGINAL).text

    @pytest.mark.parametrize(
        "text", ["Name 80% of the phases.", "Name the phases within 5 minutes."]
    )
    def test_a_made_up_number_is_refused(self, text: str) -> None:
        assert problems_of_rewrite(rewrite_answer(text=text)) == [
            "the text adds a number that is not in the original"
        ]

    def test_text_is_required(self) -> None:
        assert problems_of_rewrite(rewrite_answer(text="  ")) == ['the "text" is missing']
        assert problems_of_rewrite(json.dumps({"rationale": "x"})) == ['the "text" is missing']

    def test_text_that_is_too_long_is_refused(self) -> None:
        text = rewrite_answer(text="Name " + "a" * REWRITE_MAX_CHARS)
        assert problems_of_rewrite(text) == [
            f"the text is longer than {REWRITE_MAX_CHARS} characters"
        ]

    def test_a_rationale_is_required(self) -> None:
        assert problems_of_rewrite(rewrite_answer(rationale="")) == ["the rationale is missing"]

    def test_everything_wrong_is_reported_at_once(self) -> None:
        text = json.dumps({"text": "Name 99 things.", "rationale": 3})
        assert problems_of_rewrite(text) == [
            "the text adds a number that is not in the original",
            "the rationale is missing",
        ]

    @pytest.mark.parametrize("text", ["not json", "[]", '"x"'])
    def test_something_that_is_not_an_object_is_refused(self, text: str) -> None:
        assert problems_of_rewrite(text)[0].startswith("the answer is not")

    def test_the_model_s_words_are_never_in_a_problem(self) -> None:
        problems = problems_of_rewrite(rewrite_answer(text="Name 777 secret=hunter2 things."))
        assert "hunter2" not in " ".join(problems)


KEYS = {"L1", "L2", "L3"}


def classification(**changes: object) -> str:
    return json.dumps(
        {
            "domain": "knowledge",
            "level": "L2",
            "confidence": 0.8,
            "rationale": "It asks learners to describe.",
            **changes,
        }
    )


def problems_of_classification(text: str) -> list[str]:
    with pytest.raises(InvalidAnswer) as raised:
        parse_classification(text, level_keys=KEYS)
    return raised.value.problems


class TestClassification:
    def test_a_valid_answer(self) -> None:
        result = parse_classification(classification(), level_keys=KEYS)
        assert result.domain is ObjectiveDomain.KNOWLEDGE
        assert result.level_key == "L2" and result.confidence == Decimal("0.8")

    def test_null_means_not_sure(self) -> None:
        result = parse_classification(classification(domain=None, level=None), level_keys=KEYS)
        assert result.domain is None and result.level_key is None

    @pytest.mark.parametrize("domain", ["skill", "attitude"])
    def test_every_domain_is_accepted(self, domain: str) -> None:
        result = parse_classification(classification(domain=domain), level_keys=KEYS)
        assert result.domain is ObjectiveDomain(domain)

    def test_an_unknown_domain_is_refused(self) -> None:
        assert problems_of_classification(classification(domain="feeling")) == [
            "the domain is not knowledge, skill, attitude or null"
        ]

    @pytest.mark.parametrize("level", ["L9", "Bloom", 2, ""])
    def test_a_level_that_was_not_offered_is_refused(self, level: object) -> None:
        assert problems_of_classification(classification(level=level)) == [
            "the level is not one of the keys that were offered"
        ]

    @pytest.mark.parametrize("confidence", [-0.1, 1.5, "high", None, True])
    def test_confidence_must_be_between_zero_and_one(self, confidence: object) -> None:
        assert problems_of_classification(classification(confidence=confidence)) == [
            "the confidence must be a number from 0 to 1"
        ]

    def test_a_rationale_is_required(self) -> None:
        assert problems_of_classification(classification(rationale=" ")) == [
            "the rationale is missing"
        ]

    def test_everything_wrong_is_reported_at_once(self) -> None:
        text = classification(domain="x", level="L7", confidence=2, rationale="")
        assert len(problems_of_classification(text)) == 4
