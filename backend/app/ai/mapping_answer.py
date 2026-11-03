"""Checking the model's answer to the mapping prompt (Slice 1.16, ADR 045).

Pure functions: no database, no network. The answer is untrusted text. Only candidates that
were in the shortlist are accepted, every number is range-checked, and an evidence quote must
be words of the objective (the same rule as ``mapping.create_link``). Problems are reported as
short, fixed phrases that never repeat the model's text, so they are safe to log and to send
back in the one retry.
"""

import json
import re
from dataclasses import dataclass
from decimal import Decimal

from app.models.mapping import DepthMatch

RATIONALE_MAX = 500
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


@dataclass(frozen=True)
class Candidate:
    """One checked verdict. ``is_match`` false means the model found no link."""

    code: str
    is_match: bool
    coverage: int
    depth_match: DepthMatch
    confidence: Decimal
    rationale: str
    evidence_quote: str


class InvalidAnswer(ValueError):
    """The answer cannot be used. ``problems`` are fixed phrases, never the model's words."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def parse_answer(
    text: str,
    *,
    objective_text: str,
    codes: set[str],
    depthless: frozenset[str] | set[str] = frozenset(),
) -> list[Candidate]:
    """The verdicts in ``text`` for the codes that were offered.

    Candidates the model left out are simply absent (no suggestion); a candidate that was not
    offered, was repeated, or has a value out of range makes the answer invalid. ``depthless``
    are the codes of items that state no verb or level (keywords, topics): only for those may a
    match say ``not_applicable`` for its depth.

    Raises:
        InvalidAnswer: With every problem found.
    """
    body = _FENCE.sub("", text.strip())
    try:
        data = json.loads(body)
    except ValueError:
        raise InvalidAnswer(["the answer is not JSON"]) from None
    rows = data.get("candidates") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise InvalidAnswer(['the answer has no "candidates" list'])

    problems: list[str] = []
    found: dict[str, Candidate] = {}
    for position, row in enumerate(rows, start=1):
        label = f"candidate {position}"
        if not isinstance(row, dict):
            problems.append(f"{label} is not an object")
            continue
        code = row.get("code")
        if not isinstance(code, str) or code not in codes:
            problems.append(f"{label} names a code that was not offered")
            continue
        if code in found:
            problems.append(f"{label} repeats a code")
            continue
        verdict, issues = _verdict(row, code, objective_text, label, code in depthless)
        problems.extend(issues)
        if verdict is not None:
            found[code] = verdict
    if problems:
        raise InvalidAnswer(problems)
    return list(found.values())


def _verdict(
    row: dict[str, object], code: str, objective_text: str, label: str, depthless: bool
) -> tuple[Candidate | None, list[str]]:
    problems: list[str] = []
    is_match = row.get("is_match")
    if not isinstance(is_match, bool):
        problems.append(f"{label}: is_match must be true or false")
    coverage = row.get("coverage")
    if isinstance(coverage, bool) or not isinstance(coverage, int) or not 0 <= coverage <= 5:
        problems.append(f"{label}: coverage must be a whole number from 0 to 5")
    confidence = row.get("confidence")
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, int | float)
        or not 0 <= confidence <= 1
    ):
        problems.append(f"{label}: confidence must be a number from 0 to 1")
    depth = DepthMatch.NOT_APPLICABLE
    try:
        depth = DepthMatch(str(row.get("depth_match")))
    except ValueError:
        problems.append(f"{label}: depth_match is not one of the allowed words")
    rationale = row.get("rationale", "")
    quote = row.get("evidence_quote", "")
    if not isinstance(rationale, str) or not isinstance(quote, str):
        problems.append(f"{label}: rationale and evidence_quote must be text")
        return None, problems
    rationale = " ".join(rationale.split())[:RATIONALE_MAX]
    if is_match is True:
        if not quote.strip():
            problems.append(f"{label}: a match needs an evidence_quote")
        elif _normalise(quote) not in _normalise(objective_text):
            problems.append(f"{label}: the evidence_quote is not words of the objective")
        if not rationale:
            problems.append(f"{label}: a match needs a rationale")
        if depth is DepthMatch.NOT_APPLICABLE and not depthless:
            problems.append(
                f"{label}: not_applicable is only for an item that states no verb or level; "
                "use below, matches or above"
            )
    if problems:
        return None, problems
    assert isinstance(coverage, int) and isinstance(confidence, int | float)
    return (
        Candidate(
            code=code,
            is_match=bool(is_match),
            coverage=coverage,
            depth_match=depth,
            confidence=Decimal(str(round(float(confidence), 3))),
            rationale=rationale,
            evidence_quote=quote.strip() if is_match else "",
        ),
        [],
    )
