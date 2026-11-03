"""Checking the model's answer to the study-guide extraction prompt (Slice 1.18, ADR 047).

Pure functions, the same approach as ``mapping_answer``. The answer is untrusted text, and what it
proposes must be in the guide: every objective carries a quote that has to be words of the piece
of the guide that was sent, and wording may not contain a number the quote does not have (so a
made-up "80%" cannot enter the curriculum). Problems are fixed phrases that never repeat the
model's words.
"""

import json
import re
from dataclasses import dataclass

from app.ai.objective_answers import InvalidAnswer
from app.models.curriculum import ObjectiveDomain

OBJECTIVE_MAX_CHARS = 600
QUOTE_MAX_CHARS = 400
MAX_PER_PIECE = 30
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
_SPACE = re.compile(r"\s+")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


@dataclass(frozen=True)
class Proposed:
    text: str
    domain: ObjectiveDomain | None
    source_quote: str


def _normalise(text: str) -> str:
    return _SPACE.sub(" ", text).strip().casefold()


def _numbers(text: str) -> set[str]:
    return {n.replace(",", ".") for n in _NUMBER.findall(text)}


def parse_extraction(text: str, *, guide_text: str) -> list[Proposed]:
    """The objectives in ``text`` that are backed by ``guide_text``; none is a valid answer.

    Raises:
        InvalidAnswer: With every problem found.
    """
    try:
        data = json.loads(_FENCE.sub("", text.strip()))
    except ValueError:
        raise InvalidAnswer(["the answer is not JSON"]) from None
    rows = data.get("objectives") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise InvalidAnswer(['the answer has no "objectives" list'])
    if len(rows) > MAX_PER_PIECE:
        raise InvalidAnswer([f"there are more than {MAX_PER_PIECE} objectives"])

    guide = _normalise(guide_text)
    problems: list[str] = []
    found: dict[str, Proposed] = {}
    for position, row in enumerate(rows, start=1):
        label = f"objective {position}"
        if not isinstance(row, dict):
            problems.append(f"{label} is not an object")
            continue
        wording, quote, domain = row.get("text"), row.get("source_quote"), row.get("domain")
        if not isinstance(wording, str) or not wording.strip():
            problems.append(f'{label}: "text" is missing')
            continue
        cleaned = _SPACE.sub(" ", wording).strip()
        if len(cleaned) > OBJECTIVE_MAX_CHARS:
            problems.append(f"{label}: the text is longer than {OBJECTIVE_MAX_CHARS} characters")
        if not isinstance(quote, str) or not quote.strip():
            problems.append(f'{label}: "source_quote" is missing')
            continue
        if len(quote) > QUOTE_MAX_CHARS:
            problems.append(
                f"{label}: the source_quote is longer than {QUOTE_MAX_CHARS} characters"
            )
        elif _normalise(quote) not in guide:
            problems.append(f"{label}: the source_quote is not words of the study guide")
        elif _numbers(cleaned) - _numbers(quote):
            problems.append(f"{label}: the text has a number that is not in the source_quote")
        proposed_domain: ObjectiveDomain | None = None
        if domain is not None:
            try:
                proposed_domain = ObjectiveDomain(str(domain))
            except ValueError:
                problems.append(f"{label}: the domain is not knowledge, skill, attitude or null")
        found.setdefault(
            _normalise(cleaned), Proposed(cleaned, proposed_domain, _SPACE.sub(" ", quote).strip())
        )
    if problems:
        raise InvalidAnswer(problems)
    return list(found.values())
