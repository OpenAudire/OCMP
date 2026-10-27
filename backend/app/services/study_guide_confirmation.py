"""The study-guide confirmation: the uploader states there is no real patient information.

Every study-guide upload (Slice 1.18) must call ``confirm_no_patient_information`` before it
stores or reads the file, and must refuse the upload when it raises. The call writes an audit
event (operation ``ai.study_guide_confirmation``) with the user (the audit actor), the time,
the version of the confirmation text and a SHA-256 hash of the file's content. The file name
is **not** recorded: names of study guides can carry a person's name or a patient reference.
The privacy guard refuses any prompt with ``study_guide_text`` unless it is given the receipt
this returns (ADR 042).
"""

import hashlib
import uuid

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.confirmation import ConfirmationReceipt, issue_receipt
from app.services.audit import audit_operation, record_event
from app.services.authorization import InvalidRequestError

# Bump with the text: the i18n key is ``studyGuideConfirmation.v<N>.text`` in every locale
# (a test checks that the English text for the current version exists).
CONFIRMATION_VERSION = "1"
OPERATION = "ai.study_guide_confirmation"


class StudyGuideConfirmation(BaseModel):
    """What an upload request carries (a required field of the upload body)."""

    confirmed: bool
    # The version of the text the person saw; a stale form is refused so it is asked again.
    text_version: str


async def confirm_no_patient_information(
    db: AsyncSession,
    actor_id: uuid.UUID,
    confirmation: StudyGuideConfirmation | None,
    *,
    content: bytes,
) -> ConfirmationReceipt:
    """Check the confirmation and record it. Call this first in every study-guide upload.

    Raises:
        InvalidRequestError: If there is no confirmation, it is not ticked, or it is for
            another version of the text. Nothing is recorded then.
    """
    if confirmation is None or not confirmation.confirmed:
        raise InvalidRequestError(
            "Confirm that the study guide contains no real patient information."
        )
    if confirmation.text_version != CONFIRMATION_VERSION:
        raise InvalidRequestError("The confirmation text has changed. Read it and confirm again.")
    digest = hashlib.sha256(content).hexdigest()
    with audit_operation(OPERATION, actor_id=actor_id):
        await record_event(
            db,
            action="study_guide_confirmation",
            entity_type="study_guide",
            details={
                "text_version": CONFIRMATION_VERSION,
                "document_sha256": digest,
                "size_bytes": len(content),
            },
        )
    return issue_receipt(text_version=CONFIRMATION_VERSION, document_sha256=digest)
