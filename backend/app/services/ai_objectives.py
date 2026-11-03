"""AI help with one objective: a measurable rewrite and a suggested domain and level
(Slice 1.17, ADR 046).

Both are single interactive calls on the wording a person is typing or editing. Nothing is
saved here: the result goes back to the screen, which shows it as a word-by-word comparison (the
rewrite) or as two suggested values (the classification), and the person decides. A suggestion is
used by saving the objective in the ordinary way, with its own permission checks and audit entry.

Every call goes through ``ai_gateway.complete``, so the privacy guard, the budgets and the call
record apply. The calls of one request belong to one ``AIRun``.
"""

import asyncio
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import prompts
from app.ai.confirmation import ConfirmationReceipt
from app.ai.errors import AIError, ProviderError
from app.ai.objective_answers import (
    InvalidAnswer,
    parse_classification,
    parse_rewrite,
)
from app.ai.privacy import PromptTemplate
from app.core.config import Settings
from app.core.logging import get_logger
from app.models import AIRun, AIRunCall
from app.models.curriculum import ObjectiveDomain, ObjectiveLevel
from app.models.mapping import AIRunStatus, AIRunType
from app.services import ai_gateway, objective_checks
from app.services.objective_quality import CheckContext, LevelVerbs

logger = get_logger(__name__)

# A person is waiting, so a call that failed for a passing reason is tried once more, quickly.
RETRY_DELAY_SECONDS = 1.5
TRANSIENT_STATUSES = frozenset({408, 429, 500, 502, 503, 504, 529})
VERBS_PER_LEVEL = 12
OPTIONS_MAX_CHARS = 7_500
CUT_OFF = "the answer was cut off because it was too long; keep it short"

# What each rule-based finding says, in fixed words (never the user's text).
FINDING_PHRASES: dict[str, str] = {
    "vague_verb": "The verb is vague and cannot be assessed.",
    "multiple_verbs": "There is more than one action verb.",
    "too_long": "The objective is very long.",
    "too_short": "The objective is very short.",
    "no_action_verb": "It does not start with an action verb.",
    "learner_framing": "It describes what the teacher does, not what the learner will do.",
    "ambiguous_qualifier": "It has a qualifier that cannot be measured (such as 'appropriately').",
    "missing_domain": "",
    "missing_upward_link": "",
    "level_differs": "",
}


@dataclass(frozen=True)
class RewriteSuggestion:
    text: str
    rationale: str
    unchanged: bool
    run_id: uuid.UUID


@dataclass(frozen=True)
class ClassificationSuggestion:
    domain: ObjectiveDomain | None
    taxonomy_level_id: uuid.UUID | None
    taxonomy_level_name: str | None
    scale_name: str | None
    confidence: Decimal
    rationale: str
    run_id: uuid.UUID


def level_options(levels: list[LevelVerbs]) -> tuple[str, dict[str, LevelVerbs]]:
    """The prompt's list of taxonomy levels (keys L1, L2, ...) and the key to level map."""
    lines: list[str] = []
    keys: dict[str, LevelVerbs] = {}
    for number, level in enumerate(levels, start=1):
        key = f"L{number}"
        verbs = ", ".join(level.verbs[:VERBS_PER_LEVEL])
        lines.append(f"{key}: {level.scale_name}, {level.level_name}. Verbs: {verbs or '(none)'}")
        keys[key] = level
    text = "\n".join(lines)
    return (text[:OPTIONS_MAX_CHARS] if text else "(no taxonomy levels are set up)"), keys


def finding_lines(codes: list[str]) -> str:
    """The checker's findings as fixed sentences, one per line."""
    phrases = [FINDING_PHRASES.get(code, "") for code in codes]
    lines = [f"- {p}" for p in dict.fromkeys(phrases) if p]
    return "\n".join(lines) or "(none)"


async def _start(
    db: AsyncSession,
    settings: Settings,
    run_type: AIRunType,
    template: PromptTemplate,
    actor: uuid.UUID,
) -> AIRun:
    provider, model = await ai_gateway.ensure_ready(db, settings)
    run = AIRun(
        type=run_type,
        status=AIRunStatus.RUNNING,
        provider=provider,
        model=model,
        prompt_version=f"{template.name}:{template.version}",
        scope={"template": template.name},
        total_items=1,
        started_at=datetime.now(UTC),
        created_by_id=actor,
    )
    db.add(run)
    await db.flush()
    return run


async def _finish(db: AsyncSession, run: AIRun, status: AIRunStatus, message: str | None) -> None:
    run.status = status
    run.done_items = 1
    run.failed_items = 0 if status is AIRunStatus.SUCCEEDED else 1
    run.error_message = message
    run.finished_at = datetime.now(UTC)
    await db.flush()


async def call_with_retry(
    db: AsyncSession,
    settings: Settings,
    run: AIRun,
    template: PromptTemplate,
    fields: dict[str, str],
    transport: httpx.AsyncBaseTransport | None,
    receipt: ConfirmationReceipt | None = None,
) -> ai_gateway.GatewayResult:
    for attempt in (1, 2):
        try:
            return await ai_gateway.complete(
                db,
                settings,
                template=template,
                fields=fields,
                run_type=run.type,
                actor_id=run.created_by_id,
                run=run,
                transport=transport,
                study_guide_confirmation=receipt,
            )
        except ProviderError as exc:
            transient = exc.status_code is None or exc.status_code in TRANSIENT_STATUSES
            if attempt == 2 or not transient:
                raise
            await asyncio.sleep(RETRY_DELAY_SECONDS)
    raise AssertionError("unreachable")  # pragma: no cover


async def ask_with_retry[T](
    db: AsyncSession,
    settings: Settings,
    run: AIRun,
    template: PromptTemplate,
    fields: dict[str, str],
    transport: httpx.AsyncBaseTransport | None,
    parse: Callable[[str], T],
    receipt: ConfirmationReceipt | None = None,
) -> T:
    """One call and, if the answer is unusable, one retry that names what was wrong."""
    problems: list[str] = []
    for attempt in (1, 2):
        note = ""
        if problems:
            note = (
                "\nYour previous answer was rejected: "
                + "; ".join(problems[:5])
                + ". Answer again with valid JSON only."
            )
        result = await call_with_retry(
            db, settings, run, template, {**fields, "answer_notes": note}, transport, receipt
        )
        call = await db.get(AIRunCall, result.call_id)
        if result.truncated:
            problems = [CUT_OFF]
            if call is not None:
                call.valid = False
                call.error_message = "the answer was cut off at the token limit"
            continue
        try:
            parsed = parse(result.text)
        except InvalidAnswer as exc:
            problems = exc.problems
            if call is not None:
                call.valid = False
                call.error_message = "; ".join(problems)[:1000]
            logger.warning("objective_ai_answer_invalid", run_id=str(run.id), attempt=attempt)
            continue
        if call is not None:
            call.valid = True
        return parsed
    raise InvalidAnswer(problems)


async def rewrite(
    db: AsyncSession,
    settings: Settings,
    *,
    actor_id: uuid.UUID,
    text: str,
    level: ObjectiveLevel,
    context: CheckContext | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> RewriteSuggestion:
    """A measurable rewrite of ``text``.

    Raises:
        AIError: AI is off, restricted, over budget, or the privacy guard refused the text
            (nothing was sent).
        ProviderError: The provider failed, or its answer was unusable twice.
    """
    levels = await objective_checks.level_verbs(db)
    options, _ = level_options(levels)
    checked = await objective_checks.check_text(db, text, context or CheckContext(level=level))
    run = await _start(db, settings, AIRunType.REWRITE, prompts.REWRITE, actor_id)
    fields = {
        "objective_level": level.value,
        "objective_text": text,
        "quality_findings": finding_lines([f.code for f in checked.findings]),
        "taxonomy_options": options,
    }
    try:
        answer = await ask_with_retry(
            db,
            settings,
            run,
            prompts.REWRITE,
            fields,
            transport,
            lambda raw: parse_rewrite(raw, original=text),
        )
    except AIError as exc:
        await _finish(db, run, AIRunStatus.FAILED, str(exc)[:1000])
        raise
    except InvalidAnswer:
        await _finish(db, run, AIRunStatus.FAILED, "The answer could not be used.")
        raise ProviderError("The AI's answer could not be used. Try again.") from None
    await _finish(db, run, AIRunStatus.SUCCEEDED, None)
    return RewriteSuggestion(answer.text, answer.rationale, answer.unchanged, run.id)


async def classify(
    db: AsyncSession,
    settings: Settings,
    *,
    actor_id: uuid.UUID,
    text: str,
    level: ObjectiveLevel,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ClassificationSuggestion:
    """A suggested domain and taxonomy level for ``text``.

    Raises:
        AIError: AI is off, restricted, over budget, or the privacy guard refused the text.
        ProviderError: The provider failed, or its answer was unusable twice.
    """
    levels = await objective_checks.level_verbs(db)
    options, keys = level_options(levels)
    run = await _start(db, settings, AIRunType.CLASSIFICATION, prompts.CLASSIFY, actor_id)
    fields = {
        "objective_level": level.value,
        "objective_text": text,
        "taxonomy_options": options,
    }
    try:
        answer = await ask_with_retry(
            db,
            settings,
            run,
            prompts.CLASSIFY,
            fields,
            transport,
            lambda raw: parse_classification(raw, level_keys=set(keys)),
        )
    except AIError as exc:
        await _finish(db, run, AIRunStatus.FAILED, str(exc)[:1000])
        raise
    except InvalidAnswer:
        await _finish(db, run, AIRunStatus.FAILED, "The answer could not be used.")
        raise ProviderError("The AI's answer could not be used. Try again.") from None
    await _finish(db, run, AIRunStatus.SUCCEEDED, None)
    chosen = keys.get(answer.level_key) if answer.level_key else None
    return ClassificationSuggestion(
        domain=answer.domain,
        taxonomy_level_id=chosen.level_id if chosen else None,
        taxonomy_level_name=chosen.level_name if chosen else None,
        scale_name=chosen.scale_name if chosen else None,
        confidence=answer.confidence,
        rationale=answer.rationale,
        run_id=run.id,
    )
