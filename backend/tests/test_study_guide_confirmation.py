"""Tests for the study-guide confirmation (no real patient information), ADR 042."""

import hashlib
import json
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import privacy
from app.ai.confirmation import ConfirmationReceipt
from app.ai.errors import PrivacyViolationError
from app.models import AuditLog
from app.models.ai_settings import PersonalDataAction
from app.services.authorization import InvalidRequestError
from app.services.study_guide_confirmation import (
    CONFIRMATION_VERSION,
    OPERATION,
    StudyGuideConfirmation,
    confirm_no_patient_information,
)
from tests.factories import UserFactory

CONTENT = b"Chapter 1: the heart. Nothing about any patient."
LOCALES = Path(__file__).parents[2] / "frontend" / "src" / "i18n" / "locales"

TEMPLATE = privacy.PromptTemplate(
    name="guide",
    version="1",
    system="Summarise.",
    user="Guide: {{study_guide_text}}",
)


def ticked(version: str = CONFIRMATION_VERSION) -> StudyGuideConfirmation:
    return StudyGuideConfirmation(confirmed=True, text_version=version)


async def events(db: AsyncSession) -> list[AuditLog]:
    result = await db.scalars(select(AuditLog).where(AuditLog.entity_type == "study_guide"))
    return list(result)


class TestConfirmation:
    async def test_records_who_what_version_and_a_hash_but_no_file_name(
        self, db_session: AsyncSession
    ) -> None:
        user = UserFactory.build()
        db_session.add(user)
        await db_session.flush()

        receipt = await confirm_no_patient_information(
            db_session, user.id, ticked(), content=CONTENT
        )

        digest = hashlib.sha256(CONTENT).hexdigest()
        assert receipt.document_sha256 == digest and receipt.text_version == CONFIRMATION_VERSION
        (entry,) = await events(db_session)
        assert entry.action == "study_guide_confirmation"
        assert entry.actor_id == user.id
        assert entry.occurred_at is not None
        assert entry.context["operation"] == OPERATION
        assert entry.context["document_sha256"] == digest
        assert entry.context["text_version"] == CONFIRMATION_VERSION
        assert entry.context["size_bytes"] == len(CONTENT)
        assert "filename" not in json.dumps(entry.context).lower()

    @pytest.mark.parametrize(
        "confirmation",
        [
            None,
            StudyGuideConfirmation(confirmed=False, text_version=CONFIRMATION_VERSION),
            StudyGuideConfirmation(confirmed=True, text_version="0"),
        ],
    )
    async def test_refuses_without_a_current_confirmation_and_records_nothing(
        self, db_session: AsyncSession, confirmation: StudyGuideConfirmation | None
    ) -> None:
        user = UserFactory.build()
        db_session.add(user)
        await db_session.flush()

        with pytest.raises(InvalidRequestError):
            await confirm_no_patient_information(db_session, user.id, confirmation, content=CONTENT)

        assert await events(db_session) == []

    def test_the_text_of_the_current_version_exists_in_english(self) -> None:
        english = json.loads((LOCALES / "en.json").read_text(encoding="utf-8"))
        text = english["studyGuideConfirmation"][f"v{CONFIRMATION_VERSION}"]["text"]
        assert "patient" in text.lower()


class TestPrivacyGuardNeedsTheReceipt:
    def prepare(self, **kwargs: object) -> privacy.GuardedRequest:
        return privacy.prepare(
            TEMPLATE,
            {"study_guide_text": "The heart pumps blood."},
            known_names=None,
            action=PersonalDataAction.REFUSE,
            max_output_tokens=100,
            **kwargs,  # type: ignore[arg-type]
        )

    def test_study_guide_text_is_refused_without_the_confirmation(self) -> None:
        with pytest.raises(PrivacyViolationError, match="confirmation"):
            self.prepare()

    async def test_it_is_accepted_with_the_receipt(self, db_session: AsyncSession) -> None:
        user = UserFactory.build()
        db_session.add(user)
        await db_session.flush()
        receipt = await confirm_no_patient_information(
            db_session, user.id, ticked(), content=CONTENT
        )

        request = self.prepare(study_guide_confirmation=receipt)

        assert "The heart pumps blood." in request.messages[0].content

    def test_a_receipt_cannot_be_made_by_hand(self) -> None:
        with pytest.raises(PrivacyViolationError):
            ConfirmationReceipt("1", "0" * 64)
