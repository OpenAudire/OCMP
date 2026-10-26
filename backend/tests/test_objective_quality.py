"""Unit tests for the rule-based objective checker (no database)."""

import uuid

import pytest

from app.models.curriculum import ObjectiveDomain, ObjectiveLevel
from app.services.objective_quality import (
    CheckContext,
    LevelVerbs,
    check_objective,
    load_rules,
    strip_lead_in,
)

REMEMBER = uuid.uuid4()
UNDERSTAND = uuid.uuid4()
APPLY = uuid.uuid4()
SHOWS = uuid.uuid4()


POSITIONS: dict[str, list[str]] = {}


def levels() -> list[LevelVerbs]:
    POSITIONS.clear()

    def level(
        level_id: uuid.UUID, name: str, verbs: tuple[str, ...], scale: str = "bloom"
    ) -> LevelVerbs:
        position = len(POSITIONS.setdefault(scale, []))
        POSITIONS[scale].append(name)
        return LevelVerbs(
            level_id, name, scale, scale.title(), 0 if scale == "bloom" else 1, position, verbs
        )

    return [
        level(REMEMBER, "Remember", ("define", "list", "name", "state", "identify", "describe")),
        level(UNDERSTAND, "Understand", ("explain", "summarize", "describe", "compare")),
        level(APPLY, "Apply", ("apply", "use", "demonstrate", "solve", "analyze")),
        level(SHOWS, "Shows how", ("demonstrate", "perform"), "miller"),
    ]


FULL = CheckContext(level=ObjectiveLevel.PROGRAMME, domain=ObjectiveDomain.KNOWLEDGE)


def codes(text: str, context: CheckContext = FULL) -> list[str]:
    return [f.code for f in check_objective(text, context, levels()).findings]


class TestCleanObjective:
    def test_good_objective_has_no_findings(self) -> None:
        result = check_objective("Explain the cardiac cycle to a colleague.", FULL, levels())
        assert result.findings == []
        assert result.detected_verb == "explain"

    def test_empty_text_gives_only_context_findings(self) -> None:
        context = CheckContext(level=ObjectiveLevel.MODULE, has_parent_links=False)
        assert codes("", context) == ["missing_domain", "missing_upward_link"]


class TestVerbs:
    @pytest.mark.parametrize(
        "text",
        [
            "Understand the cardiac cycle.",
            "Know the bones of the hand.",
            "Appreciate the value of teamwork.",
            "Be aware of confidentiality rules.",
            "Learn about common infections.",
            "Become familiar with the ward routine.",
        ],
    )
    def test_vague_leading_verb_is_flagged(self, text: str) -> None:
        result = check_objective(text, FULL, levels())
        assert [f.code for f in result.findings] == ["vague_verb"]
        assert result.suggestions == []

    def test_vague_phrase_is_named_in_the_finding(self) -> None:
        finding = check_objective("Be aware of risks.", FULL, levels()).findings[0]
        assert finding.params == {"verbs": "be aware of"}

    def test_vague_verb_after_a_measurable_one_is_flagged_twice(self) -> None:
        assert set(codes("Describe the heart and understand its role.")) == {
            "vague_verb",
            "multiple_verbs",
        }

    def test_two_verbs_are_flagged(self) -> None:
        finding = check_objective(
            "Identify the organelles and state their functions.", FULL, levels()
        )
        assert [f.code for f in finding.findings] == ["multiple_verbs"]
        assert finding.findings[0].params == {"verbs": "identify, state"}

    def test_comma_separated_verbs_are_flagged(self) -> None:
        assert codes("Explain the process, compare the options, solve the case.") == [
            "multiple_verbs"
        ]

    def test_noun_after_and_is_not_a_second_verb(self) -> None:
        assert codes("Describe the signs and symptoms of shock.") == []
        assert codes("Explain the structure and function of the heart.") == []
        assert codes("Describe the plan and use of the ward.") == []

    def test_unknown_leading_word_is_an_information_finding(self) -> None:
        result = check_objective("Cardiology basics for students.", FULL, levels())
        assert [f.code for f in result.findings] == ["no_action_verb"]
        assert result.findings[0].params == {"word": "cardiology"}

    def test_inflected_and_british_spellings_match(self) -> None:
        assert check_objective("Analyse the data.", FULL, levels()).detected_verb == "analyze"
        assert check_objective("Explains the data.", FULL, levels()).detected_verb == "explain"
        assert check_objective("Summarising the data.", FULL, levels()).detected_verb == "summarize"

    def test_two_word_verb_from_the_extra_list(self) -> None:
        result = check_objective("Carry out a blood pressure check.", FULL, levels())
        assert result.detected_verb == "carry out"
        assert result.findings == []


class TestWording:
    def test_lead_in_is_stripped_and_flagged(self) -> None:
        result = check_objective(
            "By the end of the module, the student will be able to explain the heart sounds.",
            FULL,
            levels(),
        )
        assert [f.code for f in result.findings] == ["learner_framing"]
        assert result.detected_verb == "explain"

    @pytest.mark.parametrize(
        ("text", "rest"),
        [
            ("Students will explain the heart.", "explain the heart."),
            ("You will be able to explain the heart.", "explain the heart."),
            ("Be able to explain the heart.", "explain the heart."),
        ],
    )
    def test_lead_in_forms(self, text: str, rest: str) -> None:
        assert strip_lead_in(text, load_rules()) == (rest, True)

    def test_leading_to_is_dropped_quietly(self) -> None:
        assert strip_lead_in("To explain the heart.", load_rules()) == ("explain the heart.", False)

    def test_too_long(self) -> None:
        text = "Explain " + " ".join(["the heart"] * 30) + "."
        finding = check_objective(text, FULL, levels()).findings[0]
        assert finding.code == "too_long"
        assert finding.params["max"] == "40"

    def test_too_short(self) -> None:
        assert codes("Explain.") == ["too_short"]

    def test_ambiguous_qualifiers(self) -> None:
        result = check_objective("Explain the heart appropriately and well.", FULL, levels())
        assert [f.code for f in result.findings] == ["ambiguous_qualifier"]
        assert result.findings[0].params == {"words": "appropriately, well"}

    def test_qualifier_inside_another_word_is_ignored(self) -> None:
        assert codes("Explain the wellness model.") == []


class TestContext:
    def test_missing_domain_and_upward_link(self) -> None:
        context = CheckContext(level=ObjectiveLevel.LEARNING_EVENT, has_parent_links=False)
        assert codes("Explain the heart sounds.", context) == [
            "missing_domain",
            "missing_upward_link",
        ]

    def test_unknown_links_and_programme_level_skip_the_link_rule(self) -> None:
        unknown = CheckContext(level=ObjectiveLevel.MODULE, domain=ObjectiveDomain.SKILL)
        assert codes("Explain the heart sounds.", unknown) == []
        programme = CheckContext(
            level=ObjectiveLevel.PROGRAMME, domain=ObjectiveDomain.SKILL, has_parent_links=False
        )
        assert codes("Explain the heart sounds.", programme) == []

    def test_warnings_come_before_information(self) -> None:
        result = check_objective(
            "Cardiology basics.", CheckContext(level=ObjectiveLevel.PROGRAMME), levels()
        )
        assert [f.severity.value for f in result.findings] == ["warning", "info", "info"]


class TestLevelSuggestion:
    def test_suggests_every_level_the_verb_belongs_to_in_scale_order(self) -> None:
        result = check_objective("Describe the heart.", FULL, levels())
        assert [s.level_name for s in result.suggestions] == ["Remember", "Understand"]

    def test_suggests_across_scales(self) -> None:
        result = check_objective("Demonstrate hand washing.", FULL, levels())
        assert [(s.scale_key, s.level_name) for s in result.suggestions] == [
            ("bloom", "Apply"),
            ("miller", "Shows how"),
        ]

    def test_no_suggestion_without_a_known_verb(self) -> None:
        assert check_objective("Cardiology basics.", FULL, levels()).suggestions == []

    def test_no_suggestion_when_no_scale_has_verbs(self) -> None:
        assert check_objective("Explain the heart.", FULL, []).suggestions == []

    def test_chosen_level_that_differs_is_noted(self) -> None:
        context = CheckContext(
            level=ObjectiveLevel.PROGRAMME,
            domain=ObjectiveDomain.SKILL,
            taxonomy_level_id=APPLY,
        )
        result = check_objective("Explain the heart sounds.", context, levels())
        assert [f.code for f in result.findings] == ["level_differs"]
        assert result.findings[0].params["suggested"] == "Understand"

    def test_chosen_level_that_fits_is_not_noted(self) -> None:
        context = CheckContext(
            level=ObjectiveLevel.PROGRAMME,
            domain=ObjectiveDomain.SKILL,
            taxonomy_level_id=UNDERSTAND,
        )
        assert codes("Explain the heart sounds.", context) == []

    def test_chosen_level_in_another_scale_is_not_compared(self) -> None:
        context = CheckContext(
            level=ObjectiveLevel.PROGRAMME,
            domain=ObjectiveDomain.SKILL,
            taxonomy_level_id=SHOWS,
        )
        assert codes("Explain the heart sounds.", context) == []


class TestRulesFiles:
    def test_unknown_language_falls_back_to_english(self) -> None:
        assert load_rules("xx").language == "en"
        assert load_rules("../etc").language == "en"

    def test_english_rules_are_versioned(self) -> None:
        assert load_rules("en").version >= 1
