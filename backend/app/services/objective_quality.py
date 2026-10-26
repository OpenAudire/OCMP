"""Rule-based objective quality checker and taxonomy level suggestion (ADR 033).

Pure functions: no database, no network, no AI. ``check_objective`` takes the wording,
the context the rules need (level, domain, whether the objective links upward) and the
taxonomy levels with their verb lists, and returns advisory findings plus the candidate
levels for the leading verb. Nothing here blocks saving or changes data; a suggested
level is only ever offered to the person editing.

The wording lists (vague verbs and phrases, qualifiers, lead-ins, extra verbs) are
versioned data files per language in ``objective_rules/<code>.json``. Verbs that belong
to a taxonomy level live with the level (``taxonomy_levels.verbs``, the pack format), so
a scale imported from a pack brings its own verbs.
"""

import json
import re
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from functools import cache
from pathlib import Path

from app.models.curriculum import ObjectiveDomain, ObjectiveLevel

RULES_DIR = Path(__file__).parent / "objective_rules"
DEFAULT_LANGUAGE = "en"


class Severity(StrEnum):
    WARNING = "warning"  # likely to make the objective hard to assess
    INFO = "info"  # worth a look


# Every rule code with its severity. Message and advice texts are the frontend's i18n keys
# ``curriculum.quality.<code>.message`` and ``.suggestion``.
RULE_SEVERITY: dict[str, Severity] = {
    "vague_verb": Severity.WARNING,
    "multiple_verbs": Severity.WARNING,
    "too_long": Severity.WARNING,
    "missing_domain": Severity.WARNING,
    "missing_upward_link": Severity.WARNING,
    "no_action_verb": Severity.INFO,
    "too_short": Severity.INFO,
    "learner_framing": Severity.INFO,
    "ambiguous_qualifier": Severity.INFO,
    "level_differs": Severity.INFO,
}


@dataclass(frozen=True)
class Rules:
    """One language's wording rules, from ``objective_rules/<code>.json``."""

    language: str
    version: int
    min_words: int
    max_words: int
    lead_ins: tuple[re.Pattern[str], ...]
    vague_verbs: frozenset[str]
    vague_phrases: tuple[tuple[str, ...], ...]
    extra_verbs: frozenset[str]
    noun_verbs: frozenset[str]
    determiners: frozenset[str]
    connectors: tuple[str, ...]
    qualifiers: tuple[str, ...]


@dataclass(frozen=True)
class LevelVerbs:
    """A taxonomy level and the verbs that suggest it."""

    level_id: uuid.UUID
    level_name: str
    scale_key: str
    scale_name: str
    scale_position: int
    level_position: int
    verbs: tuple[str, ...]


@dataclass(frozen=True)
class Finding:
    code: str
    # Values for the message text (for example the verbs found).
    params: dict[str, str] = field(default_factory=dict)

    @property
    def severity(self) -> Severity:
        return RULE_SEVERITY[self.code]

    @property
    def message_key(self) -> str:
        return f"curriculum.quality.{self.code}.message"

    @property
    def suggestion_key(self) -> str:
        return f"curriculum.quality.{self.code}.suggestion"


@dataclass(frozen=True)
class LevelSuggestion:
    level_id: uuid.UUID
    level_name: str
    scale_key: str
    scale_name: str


@dataclass(frozen=True)
class CheckContext:
    """What the rules know about the objective besides its wording."""

    level: ObjectiveLevel
    domain: ObjectiveDomain | None = None
    taxonomy_level_id: uuid.UUID | None = None
    # None when unknown (the rule is then skipped).
    has_parent_links: bool | None = None


@dataclass(frozen=True)
class CheckResult:
    findings: list[Finding]
    detected_verb: str | None
    suggestions: list[LevelSuggestion]


def _key(word: str) -> str:
    """A word as compared: lower case, British and American spellings alike."""
    word = word.casefold().strip()
    for ending, replacement in (("ise", "ize"), ("yse", "yze")):
        if word.endswith(ending):
            return word[: -len(ending)] + replacement
    return word


@cache
def load_rules(language: str = DEFAULT_LANGUAGE) -> Rules:
    """The rules for a language; an unknown language falls back to English."""
    path = RULES_DIR / f"{language}.json"
    if not language.isalpha() or not path.is_file():
        path = RULES_DIR / f"{DEFAULT_LANGUAGE}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    return Rules(
        language=raw["language"],
        version=raw["version"],
        min_words=raw["min_words"],
        max_words=raw["max_words"],
        lead_ins=tuple(re.compile(p, re.IGNORECASE) for p in raw["lead_ins"]),
        vague_verbs=frozenset(_key(v) for v in raw["vague_verbs"]),
        vague_phrases=tuple(tuple(p.casefold().split()) for p in raw["vague_phrases"]),
        extra_verbs=frozenset(_key(v) for v in raw["extra_verbs"]),
        noun_verbs=frozenset(_key(v) for v in raw["noun_verbs"]),
        determiners=frozenset(raw["determiners"]),
        connectors=tuple(raw["connectors"]),
        qualifiers=tuple(raw["qualifiers"]),
    )


def _forms(word: str) -> set[str]:
    """The word and its base forms (explains, identifies, analysing...)."""
    word = word.casefold()
    forms = {word}
    if word.endswith("ies") and len(word) > 4:
        forms.add(word[:-3] + "y")
    if word.endswith("es") and len(word) > 3:
        forms.add(word[:-2])
    if word.endswith("s") and len(word) > 3:
        forms.add(word[:-1])
    if word.endswith("ing") and len(word) > 5:
        forms.update({word[:-3], word[:-3] + "e"})
    return {_key(f) for f in forms}


_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")


def _words(text: str) -> list[str]:
    return _WORD.findall(text)


def strip_lead_in(text: str, rules: Rules) -> tuple[str, bool]:
    """Remove "Students will be able to" style openings; True if one was removed."""
    text = " ".join(text.split())
    for pattern in rules.lead_ins:
        match = pattern.match(text)
        if match:
            return text[match.end() :], True
    if text.casefold().startswith("to "):
        return text[3:], False
    return text, False


class _Verbs:
    """The verbs the checker knows: level verbs, extra verbs and vague verbs."""

    def __init__(self, levels: list[LevelVerbs], rules: Rules) -> None:
        self.rules = rules
        self.by_verb: dict[str, list[LevelVerbs]] = {}
        for level in levels:
            for verb in level.verbs:
                self.by_verb.setdefault(_key(verb), []).append(level)
        self.known = set(self.by_verb) | set(rules.extra_verbs)

    def match(self, words: list[str]) -> tuple[str, int] | None:
        """The known verb the words start with (one or two words) and how many words."""
        if len(words) >= 2:
            pairs = {f"{form} {words[1].casefold()}" for form in _forms(words[0])}
            found = pairs & self.known
            if found:
                return sorted(found)[0], 2
        if words:
            found = _forms(words[0]) & self.known
            if found:
                return sorted(found)[0], 1
        return None

    def vague(self, words: list[str]) -> tuple[str, int] | None:
        lowered = tuple(w.casefold() for w in words)
        for parts in self.rules.vague_phrases:
            if lowered[: len(parts)] == parts:
                return " ".join(parts), len(parts)
        if words and _forms(words[0]) & self.rules.vague_verbs:
            return lowered[0], 1
        return None


def _clauses_after_connectors(text: str, rules: Rules) -> list[list[str]]:
    """The words after each connector (and, or, comma...), where a second verb would stand."""
    pieces = [text]
    for connector in rules.connectors:
        pieces = [part for piece in pieces for part in re.split(re.escape(connector), piece)]
    return [words for words in (_words(piece) for piece in pieces[1:]) if words]


def check_objective(
    text: str,
    context: CheckContext,
    levels: list[LevelVerbs],
    rules: Rules | None = None,
) -> CheckResult:
    """Check one objective's wording and context. Never raises on odd input."""
    rules = rules or load_rules()
    verbs = _Verbs(levels, rules)
    findings: list[Finding] = []
    body, framed = strip_lead_in(text, rules)
    all_words = _words(text)
    words = _words(body)

    if framed:
        findings.append(Finding("learner_framing"))
    if 0 < len(all_words) < rules.min_words:
        findings.append(Finding("too_short", {"min": str(rules.min_words)}))
    if len(all_words) > rules.max_words:
        findings.append(
            Finding("too_long", {"count": str(len(all_words)), "max": str(rules.max_words)})
        )

    detected: str | None = None
    leading: list[LevelVerbs] = []
    vague_found: list[str] = []
    more_verbs: list[str] = []
    if words:
        vague = verbs.vague(words)
        known = verbs.match(words)
        if vague:
            vague_found.append(vague[0])
            detected = vague[0]
        elif known:
            detected = known[0]
            leading = verbs.by_verb.get(known[0], [])
        else:
            findings.append(Finding("no_action_verb", {"word": words[0].casefold()}))

        # Further verbs after "and", "or" or a comma: more than one thing to assess.
        for clause in _clauses_after_connectors(body, rules):
            vague = verbs.vague(clause)
            if vague:
                vague_found.append(vague[0])
                more_verbs.append(vague[0])
                continue
            known = verbs.match(clause)
            if known is None:
                continue
            after = clause[known[1]].casefold() if len(clause) > known[1] else ""
            # Words that are also nouns (use, plan, state...) count only before a
            # determiner ("and use the...").
            if known[0] in rules.noun_verbs and after not in rules.determiners:
                continue
            more_verbs.append(known[0])

    listed = list(dict.fromkeys([detected or words[0].casefold(), *more_verbs])) if words else []
    if len(listed) > 1:
        findings.append(Finding("multiple_verbs", {"verbs": ", ".join(listed)}))
    if vague_found:
        findings.append(Finding("vague_verb", {"verbs": ", ".join(dict.fromkeys(vague_found))}))

    lowered = " " + " ".join(w.casefold() for w in all_words) + " "
    qualifiers = [q for q in rules.qualifiers if f" {q} " in lowered]
    if qualifiers:
        findings.append(Finding("ambiguous_qualifier", {"words": ", ".join(qualifiers)}))

    if context.domain is None:
        findings.append(Finding("missing_domain"))
    if context.level != ObjectiveLevel.PROGRAMME and context.has_parent_links is False:
        findings.append(Finding("missing_upward_link"))

    leading = sorted(leading, key=lambda lv: (lv.scale_position, lv.scale_name, lv.level_position))
    suggestions = [
        LevelSuggestion(lv.level_id, lv.level_name, lv.scale_key, lv.scale_name) for lv in leading
    ]
    if context.taxonomy_level_id is not None and leading:
        chosen = next((lv for lv in levels if lv.level_id == context.taxonomy_level_id), None)
        same_scale = [lv for lv in leading if chosen and lv.scale_key == chosen.scale_key]
        if chosen and same_scale and all(lv.level_id != chosen.level_id for lv in same_scale):
            findings.append(
                Finding(
                    "level_differs",
                    {
                        "verb": detected or "",
                        "chosen": chosen.level_name,
                        "suggested": ", ".join(lv.level_name for lv in same_scale),
                    },
                )
            )

    findings.sort(key=lambda f: f.severity != Severity.WARNING)
    return CheckResult(findings, detected, suggestions)
