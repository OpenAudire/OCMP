"""Tests for the privacy guard: what may be sent, what is found, redacted and refused."""

import pytest

from app.ai import privacy, prompts
from app.ai.errors import PersonalDataRefusedError, PrivacyViolationError
from app.ai.privacy import Category, GuardedRequest, PromptTemplate, detect, prepare, redact
from app.models.ai_settings import PersonalDataAction

REFUSE = PersonalDataAction.REFUSE
REDACT = PersonalDataAction.REDACT

TEMPLATE = PromptTemplate(
    name="demo",
    version="1",
    system="Compare the two texts.",
    user="Objective: {{objective_text}}\nItem: {{framework_item_text}}",
)


def categories(text: str, names: str | None = None) -> list[str]:
    pattern = privacy.known_name_pattern([names]) if names else None
    return [f.category.value for f in detect(text, pattern)]


def make(objective: str, item: str = "Describe the heart.", **kwargs: object) -> GuardedRequest:
    options: dict[str, object] = {
        "known_names": None,
        "action": REFUSE,
        "max_output_tokens": 100,
        **kwargs,
    }
    return prepare(
        TEMPLATE,
        {"objective_text": objective, "framework_item_text": item},
        **options,  # type: ignore[arg-type]
    )


class TestDetection:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Write to jane.doe@example.org about it.", ["email"]),
            ("Mail j+tag@sub.example.co.za now", ["email"]),
            ("Call 082 123 4567 today", ["phone"]),
            ("Call 0821234567 today", ["phone"]),
            ("Call +27 82 123 4567 today", ["phone"]),
            ("Call (021) 555-1234 today", ["phone"]),
            ("ID 8001015009087 on file", ["id_number"]),
            ("ID 800101 5009 087 on file", ["id_number"]),
            ("Student number: 21456789", ["student_number"]),
            ("student no. s2145678", ["student_number"]),
            ("see 21456789 for details", ["student_number"]),
            ("Reached from 192.168.1.20 yesterday", ["ip_address"]),
            ("Marked by Dr Smith last year", ["name"]),
            ("Prof. Jane Doe taught it", ["name"]),
            ("Mrs O'Brien agreed", ["name"]),
        ],
    )
    def test_finds_personal_information(self, text: str, expected: list[str]) -> None:
        assert categories(text) == expected

    @pytest.mark.parametrize(
        "text",
        [
            "Describe the anatomy of the heart and explain blood flow.",
            "NQF level 7, 120 credits, SAQA ID 12345.",
            "Year 2027, semester 2: 12 weeks of 4 contact hours.",
            "Use version 3.1.4 of the scale; ratio 0.75.",
            "Prof is a short word; Dr as well; ms alone is fine.",
            "ID number required for registration.",
            "Apply the Miller pyramid (knows, knows how, shows, does).",
        ],
    )
    def test_leaves_curriculum_text_alone(self, text: str) -> None:
        assert categories(text) == []

    def test_known_names_in_either_order_and_any_case(self) -> None:
        for text in ("Taught by Thandiwe Nkosi.", "nkosi thandiwe wrote it", "Nkosi, Thandiwe"):
            assert categories(text, "Thandiwe Nkosi") == ["name"]

    def test_single_word_names_need_four_letters_and_exact_case(self) -> None:
        assert categories("Reviewed by Zanele", "Zanele") == ["name"]
        assert categories("the zanele process", "Zanele") == []
        assert categories("Reviewed by Li", "Li") == []

    def test_a_known_name_does_not_match_inside_a_longer_word(self) -> None:
        assert categories("Nkosiana is a place", "Nkosi Thandiwe") == []

    def test_findings_do_not_overlap_an_email_wins_over_a_number(self) -> None:
        assert categories("write to s21456789@example.org") == ["email"]


class TestRedaction:
    def test_replaces_with_neutral_placeholders(self) -> None:
        text = "Mail jane@example.org or call 082 123 4567."

        assert redact(text, detect(text)) == "Mail [email removed] or call [phone removed]."

    def test_placeholders_do_not_trigger_the_detectors(self) -> None:
        text = "a@b.org 0821234567 8001015009087 192.168.0.1 Dr Smith S2145678"
        redacted = redact(text, detect(text))

        assert detect(redacted) == []


class TestPrepare:
    def test_builds_the_prompt_from_the_template_and_fields(self) -> None:
        request = make("Explain blood flow.")

        assert request.system == "Compare the two texts."
        assert (
            request.messages[0].content
            == "Objective: Explain blood flow.\nItem: Describe the heart."
        )
        assert request.max_output_tokens == 100
        assert request.redactions == {}

    def test_refuses_personal_data_and_reports_counts_not_text(self) -> None:
        with pytest.raises(PersonalDataRefusedError) as error:
            make("Ask jane@example.org or 0821234567", item="Dr Smith")

        assert error.value.findings == {
            "objective_text": {"email": 1, "phone": 1},
            "framework_item_text": {"name": 1},
        }
        message = str(error.value)
        assert "jane@example.org" not in message
        assert "0821234567" not in message
        assert "Smith" not in message
        assert "Nothing was sent" in message

    def test_redact_mode_sends_the_redacted_text_and_counts_what_it_did(self) -> None:
        request = make("Ask jane@example.org", action=REDACT)

        assert "jane" not in request.messages[0].content
        assert "[email removed]" in request.messages[0].content
        assert request.redactions == {"email": 1}

    def test_known_user_names_are_refused(self) -> None:
        names = privacy.known_name_pattern(["Thandiwe Nkosi"])

        with pytest.raises(PersonalDataRefusedError):
            make("Taught by Thandiwe Nkosi", known_names=names)

    def test_known_user_names_are_redacted_in_redact_mode(self) -> None:
        names = privacy.known_name_pattern(["Thandiwe Nkosi"])

        request = make("Taught by Thandiwe Nkosi", known_names=names, action=REDACT)

        assert "Nkosi" not in request.messages[0].content

    def test_fields_must_match_the_template_exactly(self) -> None:
        with pytest.raises(PrivacyViolationError, match="exactly"):
            prepare(
                TEMPLATE,
                {"objective_text": "x"},
                known_names=None,
                action=REFUSE,
                max_output_tokens=10,
            )
        with pytest.raises(PrivacyViolationError, match="exactly"):
            prepare(
                TEMPLATE,
                {"objective_text": "x", "framework_item_text": "y", "student_name": "z"},
                known_names=None,
                action=REFUSE,
                max_output_tokens=10,
            )

    def test_text_that_is_too_long_is_refused(self) -> None:
        with pytest.raises(PrivacyViolationError, match="longer"):
            make("x" * 4_001)

    def test_a_template_cannot_use_a_field_that_is_not_allowed(self) -> None:
        with pytest.raises(PrivacyViolationError, match="not allowed"):
            PromptTemplate(name="bad", version="1", system="s", user="Hello {{student_name}}")

    def test_a_system_prompt_cannot_take_fields(self) -> None:
        with pytest.raises(PrivacyViolationError, match="system prompt"):
            PromptTemplate(name="bad", version="1", system="Hi {{objective_text}}", user="u")

    def test_a_schema_is_added_to_the_system_prompt(self) -> None:
        template = PromptTemplate(
            name="s",
            version="1",
            system="Answer.",
            user="Text: {{objective_text}}",
            json_schema={"type": "object"},
        )

        request = prepare(
            template,
            {"objective_text": "x"},
            known_names=None,
            action=REFUSE,
            max_output_tokens=10,
        )

        assert request.system.startswith("Answer.")
        assert '{"type":"object"}' in request.system

    def test_the_final_text_is_scanned_too(self) -> None:
        template = PromptTemplate(
            name="leaky",
            version="1",
            system="Contact helpdesk@example.org.",
            user="Text: {{objective_text}}",
        )

        with pytest.raises(PersonalDataRefusedError) as error:
            prepare(
                template,
                {"objective_text": "fine"},
                known_names=None,
                action=REFUSE,
                max_output_tokens=10,
            )

        assert "prompt" in error.value.findings

    def test_the_connection_test_prompt_is_fixed_and_clean(self) -> None:
        assert prompts.CONNECTION_TEST.field_names == ()
        request = prepare(
            prompts.CONNECTION_TEST,
            {},
            known_names=None,
            action=REFUSE,
            max_output_tokens=10,
        )
        assert "ready" in request.messages[0].content


class TestSeal:
    def test_a_request_cannot_be_built_outside_the_guard(self) -> None:
        with pytest.raises(PrivacyViolationError, match="privacy guard"):
            GuardedRequest(
                template_name="x",
                template_version="1",
                system="s",
                messages=(),
                json_schema=None,
                max_output_tokens=1,
                temperature=None,
            )

    def test_a_forged_seal_is_refused(self) -> None:
        with pytest.raises(PrivacyViolationError):
            GuardedRequest(
                template_name="x",
                template_version="1",
                system="s",
                messages=(),
                json_schema=None,
                max_output_tokens=1,
                temperature=None,
                _seal=object(),
            )

    def test_the_stored_record_is_exactly_what_was_sent(self) -> None:
        record = make("Explain blood flow.").as_record()

        assert record["template"] == "demo"
        assert record["messages"] == [
            {"role": "user", "content": "Objective: Explain blood flow.\nItem: Describe the heart."}
        ]


def test_every_allowed_field_is_curriculum_text() -> None:
    """The allow-list holds no field that names a person."""
    forbidden = ("name_of", "student", "staff", "user", "email", "phone", "grade", "mark")
    for name in privacy.ALLOWED_FIELDS:
        assert not any(word in name for word in forbidden), name
    assert Category.NAME.value == "name"
