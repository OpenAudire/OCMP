"""The privacy guard: nothing reaches an AI provider except through ``prepare`` (ADR 042).

Rules, enforced here in code:

1. A prompt is a code-owned ``PromptTemplate`` with ``{{placeholders}}``. Placeholders may
   only be names on ``ALLOWED_FIELDS`` (curriculum text, never people), and the caller must
   supply exactly those fields. Anything else is refused.
2. Every field value is scanned for personal information: email addresses, phone numbers,
   South African ID numbers, student and staff numbers, long ID-like digit runs, IP
   addresses, titles followed by a name ("Dr Smith"), and the names of the users of this
   installation.
3. By default a finding **refuses** the call. If the institution chose redaction, the text
   is replaced with placeholders and scanned again; anything left refuses.
4. The assembled messages are scanned once more before the request is sealed.
5. Adapters accept only a sealed ``GuardedRequest``, which only this module can build.

The guard reports counts per field and category, never the text it found.
"""

import json
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.errors import PersonalDataRefusedError, PrivacyViolationError
from app.models import User
from app.models.ai_settings import PersonalDataAction


class Category(StrEnum):
    EMAIL = "email"
    PHONE = "phone"
    ID_NUMBER = "id_number"
    STUDENT_NUMBER = "student_number"
    IP_ADDRESS = "ip_address"
    NAME = "name"


_PLACEHOLDER_TEXT = {
    Category.EMAIL: "[email removed]",
    Category.PHONE: "[phone removed]",
    Category.ID_NUMBER: "[id number removed]",
    Category.STUDENT_NUMBER: "[number removed]",
    Category.IP_ADDRESS: "[address removed]",
    Category.NAME: "[name removed]",
}

# Curriculum text only. A new entry needs a review: it must never hold a person's data.
# The value is the longest text accepted for that field, in characters.
ALLOWED_FIELDS: dict[str, int] = {
    "programme_title": 300,
    "module_title": 300,
    "module_description": 4_000,
    "event_title": 300,
    "event_description": 4_000,
    "objective_text": 4_000,
    "objective_level": 50,
    "domain_name": 100,
    "taxonomy_level_name": 100,
    "framework_name": 300,
    "framework_item_code": 100,
    "framework_item_text": 4_000,
    "framework_candidates": 40_000,
    "study_guide_text": 60_000,
}

# Ordered by priority: earlier patterns win where matches overlap.
_PATTERNS: tuple[tuple[Category, re.Pattern[str]], ...] = (
    (Category.EMAIL, re.compile(r"[\w.%+\-]+@[\w\-]+(?:\.[\w\-]+)+")),
    (Category.ID_NUMBER, re.compile(r"(?<!\d)\d{6}[ \-]?\d{4}[ \-]?\d{3}(?!\d)")),
    (
        Category.STUDENT_NUMBER,
        re.compile(
            r"\b(?:student|staff|employee|personnel|passport|identity|id)\s*"
            r"(?:number|no\.?|nr\.?|#)\s*[:#]?\s*(?=[A-Za-z0-9\-]*\d)[A-Za-z0-9][A-Za-z0-9\-]{3,}",
            re.IGNORECASE,
        ),
    ),
    (
        Category.PHONE,
        re.compile(
            r"(?<![\w])(?:\+|00)\d{1,3}[\s\-.()]*\d(?:[\s\-.()]*\d){6,}(?!\w)"
            r"|(?<![\w.])\(?0\d{1,2}\)?[\s\-.]?\d{3}[\s\-.]?\d{3,4}(?![\w])"
            r"|(?<![\w.])\d{3}[\s\-.]\d{3}[\s\-.]\d{3,4}(?![\w.])"
        ),
    ),
    (Category.IP_ADDRESS, re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")),
    (Category.STUDENT_NUMBER, re.compile(r"(?<![\w.])\d{7,12}(?![\w])|\b[A-Za-z]{1,2}\d{7,9}\b")),
    (
        Category.NAME,
        re.compile(
            r"\b(?:Dr|Prof|Professor|Mr|Mrs|Ms|Miss|Mx|Mnr|Mev|Adv)\b\.?\s+"
            r"[A-Z][\w'\N{RIGHT SINGLE QUOTATION MARK}\-]+"
            r"(?:\s+[A-Z][\w'\N{RIGHT SINGLE QUOTATION MARK}\-]+)?"
        ),
    ),
)

_PLACEHOLDER_RE = re.compile(r"\{\{([a-z_]+)\}\}")
_MIN_SINGLE_NAME = 4
_MAX_KNOWN_NAMES = 50_000


@dataclass(frozen=True)
class Finding:
    category: Category
    start: int
    end: int


def known_name_pattern(names: Iterable[str]) -> re.Pattern[str] | None:
    """A pattern for the names of this installation's users, in common written orders.

    Names of several words match as a whole (either order, with or without a comma) in
    any letter case. A single-word name of four or more letters matches as a whole,
    capitalised word. Shorter single words are not matched: they would block ordinary text.
    """
    alternatives: set[str] = set()
    for raw in list(names)[:_MAX_KNOWN_NAMES]:
        tokens = [t for t in re.split(r"[\s,]+", raw.strip()) if t]
        if not tokens:
            continue
        if len(tokens) == 1:
            if len(tokens[0]) >= _MIN_SINGLE_NAME:
                alternatives.add("(?-i:" + re.escape(tokens[0]) + ")")
            continue
        forward = r"[\s,]+".join(re.escape(t) for t in tokens)
        backward = r"[\s,]+".join(re.escape(t) for t in reversed(tokens))
        alternatives.add(forward)
        alternatives.add(backward)
        if len(tokens) > 2:
            alternatives.add(re.escape(tokens[0]) + r"[\s,]+" + re.escape(tokens[-1]))
    if not alternatives:
        return None
    ordered = sorted(alternatives, key=len, reverse=True)
    return re.compile(r"(?<!\w)(?:" + "|".join(ordered) + r")(?!\w)", re.IGNORECASE)


def detect(text: str, known_names: re.Pattern[str] | None = None) -> list[Finding]:
    """Personal information found in ``text``, without overlaps, in text order."""
    found: list[tuple[int, int, int, Category]] = []
    for priority, (category, pattern) in enumerate(_PATTERNS):
        found.extend((m.start(), m.end(), priority, category) for m in pattern.finditer(text))
    if known_names is not None:
        found.extend((m.start(), m.end(), 99, Category.NAME) for m in known_names.finditer(text))
    found.sort(key=lambda f: (f[0], -(f[1] - f[0]), f[2]))
    findings: list[Finding] = []
    last_end = -1
    for start, end, _priority, category in found:
        if start >= last_end:
            findings.append(Finding(category, start, end))
            last_end = end
    return findings


def redact(text: str, findings: list[Finding]) -> str:
    """Replace each finding with a neutral placeholder."""
    for f in sorted(findings, key=lambda f: f.start, reverse=True):
        text = text[: f.start] + _PLACEHOLDER_TEXT[f.category] + text[f.end :]
    return text


async def load_known_names(db: AsyncSession) -> re.Pattern[str] | None:
    """Pattern for the display names of every user of this installation."""
    result = await db.execute(select(User.display_name))
    return known_name_pattern(row[0] for row in result.all() if row[0])


@dataclass(frozen=True)
class PromptTemplate:
    """A prompt owned by the code. Its placeholders must be on ``ALLOWED_FIELDS``."""

    name: str
    version: str
    system: str
    user: str
    json_schema: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if _PLACEHOLDER_RE.search(self.system):
            raise PrivacyViolationError("A system prompt cannot take fields.")
        unknown = set(self.field_names) - set(ALLOWED_FIELDS)
        if unknown:
            raise PrivacyViolationError(
                f"Template {self.name} uses fields that are not allowed: {sorted(unknown)}."
            )

    @property
    def field_names(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(_PLACEHOLDER_RE.findall(self.user)))


@dataclass(frozen=True)
class GuardedMessage:
    role: str
    content: str


_SEAL = object()


@dataclass(frozen=True)
class GuardedRequest:
    """A request that passed the guard. Only ``prepare`` can make one."""

    template_name: str
    template_version: str
    system: str
    messages: tuple[GuardedMessage, ...]
    json_schema: dict[str, Any] | None
    max_output_tokens: int
    temperature: float | None
    # Category -> how many pieces were replaced (redaction mode); counts only.
    redactions: dict[str, int] = field(default_factory=dict)
    _seal: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._seal is not _SEAL:
            raise PrivacyViolationError("A GuardedRequest can only be made by the privacy guard.")

    def as_record(self) -> dict[str, Any]:
        """What is stored with the AI call: the exact text that was sent."""
        return {
            "template": self.template_name,
            "version": self.template_version,
            "system": self.system,
            "messages": [{"role": m.role, "content": m.content} for m in self.messages],
            "redactions": self.redactions,
        }


def prepare(
    template: PromptTemplate,
    fields: dict[str, str],
    *,
    known_names: re.Pattern[str] | None,
    action: PersonalDataAction,
    max_output_tokens: int,
    temperature: float | None = None,
) -> GuardedRequest:
    """Check, if needed redact, and seal a request.

    Raises:
        PrivacyViolationError: If the fields are not exactly the template's allowed fields.
        PersonalDataRefusedError: If personal information is found and not removable.
    """
    expected = set(template.field_names)
    if set(fields) != expected:
        raise PrivacyViolationError(
            f"Fields for {template.name} must be exactly {sorted(expected)}; got {sorted(fields)}."
        )

    refused: dict[str, dict[str, int]] = {}
    clean: dict[str, str] = {}
    redactions: Counter[str] = Counter()
    for name, value in fields.items():
        if not isinstance(value, str):
            raise PrivacyViolationError(f"Field {name} must be text.")
        if len(value) > ALLOWED_FIELDS[name]:
            raise PrivacyViolationError(f"Field {name} is longer than {ALLOWED_FIELDS[name]}.")
        findings = detect(value, known_names)
        if not findings:
            clean[name] = value
            continue
        if action is PersonalDataAction.REFUSE:
            refused[name] = dict(Counter(f.category.value for f in findings))
            continue
        redacted = redact(value, findings)
        leftover = detect(redacted, known_names)
        if leftover:
            refused[name] = dict(Counter(f.category.value for f in leftover))
            continue
        redactions.update(f.category.value for f in findings)
        clean[name] = redacted
    if refused:
        raise PersonalDataRefusedError(refused)

    user_text = _PLACEHOLDER_RE.sub(lambda m: clean[m.group(1)], template.user)
    system = template.system
    if template.json_schema is not None:
        schema_text = json.dumps(template.json_schema, separators=(",", ":"), sort_keys=True)
        system += "\n\nReply with JSON only. It must match this JSON schema:\n" + schema_text
    # Last line of defence: scan exactly what will be sent.
    final = detect(system + "\n" + user_text, known_names)
    if final:
        raise PersonalDataRefusedError({"prompt": dict(Counter(f.category.value for f in final))})

    return GuardedRequest(
        template_name=template.name,
        template_version=template.version,
        system=system,
        messages=(GuardedMessage("user", user_text),),
        json_schema=template.json_schema,
        max_output_tokens=max_output_tokens,
        temperature=temperature,
        redactions=dict(redactions),
        _seal=_SEAL,
    )
