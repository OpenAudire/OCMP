"""Checking the model's answers to the rewrite and classification prompts (Slice 1.17, ADR 046).

Pure functions: no database, no network. Answers are untrusted text. Problems are fixed phrases
that never repeat the model's words, so they are safe to log and to send back in the one retry
(the same rule as ``mapping_answer``).
"""

import json
import re
from dataclasses import dataclass
from decimal import Decimal

from app.models.curriculum import ObjectiveDomain

REWRITE_MAX_CHARS = 600
RATIONALE_MAX = 400
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_SPACE = re.compile(r"\s+")


class InvalidAnswer(ValueError):
    """The answer cannot be used. ``problems`` are fixed phrases, never the model's words."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class Rewrite:
    text: str
    rationale: str
    # The model found the objective already measurable and returned it as it was.
    unchanged: bool


@dataclass(frozen=True)
class Classification:
    domain: ObjectiveDomain | None
    # One of the option keys that were offered ("L1", "L2", ...), or None when unsure.
    level_key: str | None
    confidence: Decimal
    rationale: str


def _object(text: str) -> dict[str, object]:
    try:
        data = json.loads(_FENCE.sub("", text.strip()))
    except ValueError:
        raise InvalidAnswer(["the answer is not JSON"]) from None
    if not isinstance(data, dict):
        raise InvalidAnswer(["the answer is not a JSON object"])
    return data


def _rationale(data: dict[str, object], problems: list[str]) -> str:
    value = data.get("rationale")
    if not isinstance(value, str) or not value.strip():
        problems.append("the rationale is missing")
        return ""
    return _SPACE.sub(" ", value).strip()[:RATIONALE_MAX]


def _numbers(text: str) -> set[str]:
    return {n.replace(",", ".") for n in _NUMBER.findall(text)}


def parse_rewrite(text: str, *, original: str) -> Rewrite:
    """The rewrite in ``text``.

    The new wording must be non-empty text of reasonable length that adds no number the
    original did not have (a made-up "80%" or "within 5 minutes" would invent a standard).

    Raises:
        InvalidAnswer: With every problem found.
    """
    data = _object(text)
    problems: list[str] = []
    wording = data.get("text")
    cleaned = ""
    if not isinstance(wording, str) or not wording.strip():
        problems.append('the "text" is missing')
    else:
        cleaned = _SPACE.sub(" ", wording).strip()
        if len(cleaned) > REWRITE_MAX_CHARS:
            problems.append(f"the text is longer than {REWRITE_MAX_CHARS} characters")
        if _numbers(cleaned) - _numbers(original):
            problems.append("the text adds a number that is not in the original")
    rationale = _rationale(data, problems)
    if problems:
        raise InvalidAnswer(problems)
    same = _SPACE.sub(" ", original).strip().casefold() == cleaned.casefold()
    return Rewrite(text=cleaned, rationale=rationale, unchanged=same)


def parse_classification(text: str, *, level_keys: set[str]) -> Classification:
    """The domain and level in ``text``; ``null`` for either means the model was unsure.

    Raises:
        InvalidAnswer: With every problem found.
    """
    data = _object(text)
    problems: list[str] = []
    domain: ObjectiveDomain | None = None
    raw_domain = data.get("domain")
    if raw_domain is not None:
        try:
            domain = ObjectiveDomain(str(raw_domain))
        except ValueError:
            problems.append("the domain is not knowledge, skill, attitude or null")
    level_key: str | None = None
    raw_level = data.get("level")
    if raw_level is not None:
        if isinstance(raw_level, str) and raw_level in level_keys:
            level_key = raw_level
        else:
            problems.append("the level is not one of the keys that were offered")
    confidence = data.get("confidence")
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, int | float)
        or not 0 <= confidence <= 1
    ):
        problems.append("the confidence must be a number from 0 to 1")
        confidence = 0
    rationale = _rationale(data, problems)
    if problems:
        raise InvalidAnswer(problems)
    return Classification(domain, level_key, Decimal(str(round(float(confidence), 3))), rationale)
