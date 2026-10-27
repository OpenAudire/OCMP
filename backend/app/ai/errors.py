"""Errors of the AI layer. Messages are safe to show to an admin and never hold content."""


class AIError(Exception):
    """Base class. ``code`` is a stable machine-readable reason."""

    code = "ai_error"


class AIRefusedError(AIError):
    """The call was refused before anything was sent."""

    code = "refused"


class AIDisabledError(AIRefusedError):
    code = "ai_disabled"

    def __init__(self) -> None:
        super().__init__("AI is switched off. Choose a provider in Admin > AI settings.")


class AINotConfiguredError(AIRefusedError):
    code = "not_configured"


class AILocalOnlyError(AIRefusedError):
    code = "local_only"

    def __init__(self) -> None:
        super().__init__(
            "Local-only mode is on, and the chosen provider is not on this server or "
            "network. Nothing was sent."
        )


class AIAcknowledgementMissingError(AIRefusedError):
    code = "acknowledgement_missing"

    def __init__(self) -> None:
        super().__init__(
            "This provider processes text outside South Africa and an administrator has "
            "not acknowledged that yet. Nothing was sent."
        )


class AIBudgetExceededError(AIRefusedError):
    code = "budget_exceeded"


class PersonalDataRefusedError(AIRefusedError):
    """The privacy guard found personal data and refused to send the text."""

    code = "personal_data"

    def __init__(self, findings: dict[str, dict[str, int]]) -> None:
        self.findings = findings  # field -> category -> count; never the text itself
        parts = [
            f"{field}: " + ", ".join(f"{n} {cat}" for cat, n in sorted(cats.items()))
            for field, cats in sorted(findings.items())
        ]
        super().__init__(
            "The text looks like it contains personal information (" + "; ".join(parts) + "). "
            "Nothing was sent. Remove it and try again."
        )


class PrivacyViolationError(AIError):
    """The request itself breaks the privacy rules (a programming error, not user data)."""

    code = "privacy_violation"


class ProviderError(AIError):
    """The provider could not be reached or answered with an error."""

    code = "provider_error"

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(message)


class ProviderNotVerifiedError(AIError):
    """An adapter whose interface could not be checked against current documentation."""

    code = "not_verified"
