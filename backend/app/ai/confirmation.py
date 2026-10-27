"""Proof that the uploader confirmed a study guide holds no real patient information.

A ``ConfirmationReceipt`` can only be made by
``app.services.study_guide_confirmation.confirm_no_patient_information``, which records the
confirmation in the audit log. The privacy guard refuses any prompt that uses the
``study_guide_text`` field without one, so a study-guide feature cannot reach an AI provider
without the confirmation having been asked for and recorded (ADR 042).
"""

from dataclasses import dataclass, field

from app.ai.errors import PrivacyViolationError

_SEAL = object()


@dataclass(frozen=True)
class ConfirmationReceipt:
    """What was confirmed: the text version and a hash of the document, never its name."""

    text_version: str
    document_sha256: str
    _seal: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._seal is not _SEAL:
            raise PrivacyViolationError(
                "A ConfirmationReceipt can only be made by confirm_no_patient_information."
            )


def issue_receipt(*, text_version: str, document_sha256: str) -> ConfirmationReceipt:
    """Make a receipt. Only the confirmation service calls this, after recording the event."""
    return ConfirmationReceipt(text_version, document_sha256, _seal=_SEAL)
