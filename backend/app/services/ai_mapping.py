"""The AI mapping pipeline (Slice 1.16, ADR 045).

A run maps the objectives of a draft version (or one module of it) to one framework:

1. a shortlist of the framework's items for each objective (``mapping_shortlist``);
2. one guarded call per objective with the versioned prompt (``prompts.MAPPING``), carrying a
   few earlier reviewer decisions on similar objectives as examples;
3. the answer is checked (``mapping_answer``); an invalid answer is retried once, and an
   objective that still fails is counted as failed and skipped;
4. matches are saved as ``suggested`` links of source AI that name the run. Nothing is ever
   accepted here: people decide in the review queue (brief, section 8).

Progress is on the run row (``total_items``, ``done_items``, ``failed_items``,
``links_created``) so a screen can show it while the job works. A run stops at once when the
monthly budget is reached (``budget_exceeded``), when AI is turned off or restricted
meanwhile, or after three provider failures in a row; a person can cancel it between objectives.
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import httpx
from redis.asyncio import Redis
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import prompts
from app.ai.embeddings import MODEL_KEY, EmbeddingProvider
from app.ai.errors import (
    AIBudgetExceededError,
    AIError,
    AIRefusedError,
    PersonalDataRefusedError,
    ProviderError,
)
from app.ai.mapping_answer import Candidate, InvalidAnswer, parse_answer
from app.core.config import Settings
from app.core.logging import get_logger
from app.models import (
    AIRun,
    AIRunCall,
    CurriculumVersion,
    Framework,
    FrameworkItem,
    LearningEvent,
    Module,
    Objective,
)
from app.models.curriculum import ObjectiveLevel, ObjectiveStatus
from app.models.framework import FrameworkStatus
from app.models.mapping import AIRunStatus, AIRunType, MappingSource
from app.services import ai_gateway, mapping
from app.services.audit import audit_operation
from app.services.authorization import ConflictError, InvalidRequestError
from app.services.curriculum_edit import ensure_editable
from app.services.mapping_shortlist import DEFAULT_K, shortlist
from app.services.mapping_shortlist import Candidate as Shortlisted

logger = get_logger(__name__)

MIN_K, MAX_K = 3, 20
EXAMPLES = 4
EXAMPLE_FLOOR = 0.88
TEXT_CUT = 500
# A run gives up when the provider fails this many objectives one after another.
MAX_IN_ROW = 3
ACTIVE = (AIRunStatus.QUEUED, AIRunStatus.RUNNING)

_EXAMPLES_SQL = text(
    """
    WITH me AS (
        SELECT vector FROM embeddings
        WHERE entity_type = 'objective' AND entity_id = :objective_id AND model_key = :key
    )
    SELECT o.text, i.code, i.title, l.status, l.coverage,
           1 - (e.vector <=> me.vector) AS similarity
    FROM mapping_links l
    JOIN objectives o ON o.id = l.objective_id AND o.deleted_at IS NULL
    JOIN framework_items i ON i.id = l.framework_item_id
    JOIN embeddings e
      ON e.entity_id = o.id AND e.entity_type = 'objective' AND e.model_key = :key,
    me
    WHERE l.status IN ('accepted', 'rejected') AND l.deleted_at IS NULL
      AND i.framework_id = :framework_id AND o.id <> :objective_id
      AND 1 - (e.vector <=> me.vector) >= :floor
    ORDER BY similarity DESC
    LIMIT :limit
    """
)


def _cut(value: str, size: int = TEXT_CUT) -> str:
    value = " ".join(value.split())
    return value if len(value) <= size else value[: size - 1] + "…"


# --- Starting a run -----------------------------------------------------------------------


async def scope_objectives(
    db: AsyncSession, version_id: uuid.UUID, module_id: uuid.UUID | None
) -> list[Objective]:
    """The live, non-retired objectives a run covers: the whole version, or one module's
    outcomes and the objectives of its sessions. Programme outcomes first, then module
    outcomes, then session objectives."""
    query = (
        select(Objective)
        .where(
            Objective.version_id == version_id,
            Objective.deleted_at.is_(None),
            Objective.status != ObjectiveStatus.RETIRED,
        )
        .order_by(
            Objective.level != ObjectiveLevel.PROGRAMME,
            Objective.level != ObjectiveLevel.MODULE,
            Objective.position,
            Objective.created_at,
        )
    )
    if module_id is not None:
        sessions = select(LearningEvent.id).where(
            LearningEvent.module_id == module_id, LearningEvent.deleted_at.is_(None)
        )
        query = query.where(
            or_(Objective.module_id == module_id, Objective.learning_event_id.in_(sessions))
        )
    return list(await db.scalars(query))


async def start_run(
    db: AsyncSession,
    settings: Settings,
    *,
    actor_id: uuid.UUID,
    version: CurriculumVersion,
    framework: Framework,
    module: Module | None = None,
    top_k: int = DEFAULT_K,
) -> AIRun:
    """Check everything that can be checked now and queue a run (the caller queues the job).

    Raises:
        ConflictError: If the version is not a draft, or a run of this version and framework is
            queued or running.
        InvalidRequestError: For a framework that is not usable, a module of another version,
            a shortlist size out of range, or no objectives in scope.
        AIRefusedError: If AI is off, restricted or not set up (nothing was made).
    """
    ensure_editable(version)
    if framework.is_deleted or framework.status == FrameworkStatus.DRAFT:
        raise InvalidRequestError("Choose a framework that is in use.")
    if module is not None and module.version_id != version.id:
        raise InvalidRequestError("That module is not in this version.")
    if not MIN_K <= top_k <= MAX_K:
        raise InvalidRequestError(f"The shortlist size must be between {MIN_K} and {MAX_K}.")
    objectives = await scope_objectives(db, version.id, module.id if module else None)
    if not objectives:
        raise InvalidRequestError("There are no objectives to map in this scope.")
    scope = {
        "version_id": str(version.id),
        "framework_id": str(framework.id),
        "module_id": str(module.id) if module else None,
    }
    running = await db.scalars(
        select(AIRun).where(AIRun.type == AIRunType.MAPPING, AIRun.status.in_(ACTIVE))
    )
    if any(
        r.scope.get("version_id") == scope["version_id"]
        and r.scope.get("framework_id") == scope["framework_id"]
        for r in running
    ):
        raise ConflictError("A mapping run for this version and framework is already going.")
    provider, model = await ai_gateway.ensure_ready(db, settings)
    run = AIRun(
        type=AIRunType.MAPPING,
        status=AIRunStatus.QUEUED,
        provider=provider,
        model=model,
        prompt_version=f"{prompts.MAPPING.name}:{prompts.MAPPING.version}",
        parameters={"top_k": top_k},
        scope=scope,
        total_items=len(objectives),
        created_by_id=actor_id,
    )
    db.add(run)
    await db.flush()
    return run


async def cancel_run(db: AsyncSession, run: AIRun) -> AIRun:
    """Stop a run that has not finished; a running job stops before its next objective."""
    if run.status in ACTIVE:
        run.status = AIRunStatus.CANCELLED
        run.finished_at = datetime.now(UTC)
        await db.flush()
    return run


# --- Running ------------------------------------------------------------------------------


def candidate_lines(shortlisted: list[Shortlisted]) -> str:
    """The shortlist as the prompt shows it: one line per item, code first."""
    lines = []
    for entry in shortlisted:
        item = entry.item
        wording = item.title.strip()
        if item.description.strip():
            wording = f"{wording}. {item.description.strip()}"
        lines.append(f"{item.code}: {_cut(wording)}")
    return "\n".join(lines)


async def example_lines(
    db: AsyncSession, objective: Objective, framework_id: uuid.UUID, settings: Settings
) -> str:
    """Earlier reviewer decisions on similar objectives, as guidance (empty without embeddings
    or without precedent). Accepted and rejected links are both shown; rejections are how the
    model learns what an institution does not count."""
    if not settings.embeddings_local:
        return ""
    rows = (
        await db.execute(
            _EXAMPLES_SQL,
            {
                "objective_id": objective.id,
                "framework_id": framework_id,
                "key": MODEL_KEY,
                "floor": EXAMPLE_FLOOR,
                "limit": EXAMPLES,
            },
        )
    ).all()
    if not rows:
        return ""
    lines = ["Earlier decisions by this institution's reviewers on similar objectives:"]
    for wording, code, title, status, coverage in (r[:5] for r in rows):
        verdict = f"accepted, coverage {coverage}" if status == "accepted" else "rejected"
        lines.append(
            f'- Objective: "{_cut(wording, 300)}" | Item {code}: {_cut(title, 200)} | {verdict}'
        )
    return "\n".join(lines) + "\n"


async def _ask(
    db: AsyncSession,
    settings: Settings,
    run: AIRun,
    objective: Objective,
    framework: Framework,
    shortlisted: list[Shortlisted],
    examples: str,
    transport: httpx.AsyncBaseTransport | None,
) -> list[Candidate]:
    """One call and, if the answer is unusable, one retry that names what was wrong."""
    codes = {entry.item.code for entry in shortlisted}
    base_fields = {
        "framework_name": framework.name,
        "objective_level": objective.level.value,
        "objective_text": objective.text,
        "framework_candidates": candidate_lines(shortlisted),
    }
    problems: list[str] = []
    for attempt in (1, 2):
        notes = examples
        if problems:
            notes += (
                "Your previous answer was rejected: "
                + "; ".join(problems[:6])
                + ". Answer again with valid JSON only.\n"
            )
        result = await ai_gateway.complete(
            db,
            settings,
            template=prompts.MAPPING,
            fields={**base_fields, "mapping_examples": notes},
            run_type=AIRunType.MAPPING,
            actor_id=run.created_by_id,
            run=run,
            transport=transport,
        )
        call = await db.get(AIRunCall, result.call_id)
        try:
            verdicts = parse_answer(result.text, objective_text=objective.text, codes=codes)
        except InvalidAnswer as exc:
            problems = exc.problems
            if call is not None:
                call.valid = False
                call.error_message = "; ".join(problems)[:1000]
            logger.warning("mapping_answer_invalid", run_id=str(run.id), attempt=attempt)
            continue
        if call is not None:
            call.valid = True
        return verdicts
    raise InvalidAnswer(problems)


async def _map_objective(
    db: AsyncSession,
    settings: Settings,
    run: AIRun,
    objective: Objective,
    framework: Framework,
    k: int,
    transport: httpx.AsyncBaseTransport | None,
    embedder: EmbeddingProvider | None,
    redis: Redis | None,
) -> int | None:
    """Suggestions made for one objective; ``None`` when there was nothing to ask about."""
    chosen = await shortlist(
        db, settings, objective, framework.id, k=k, provider=embedder, redis=redis
    )
    if not chosen.candidates:
        return None
    examples = await example_lines(db, objective, framework.id, settings)
    verdicts = await _ask(
        db, settings, run, objective, framework, chosen.candidates, examples, transport
    )
    by_code: dict[str, FrameworkItem] = {c.item.code: c.item for c in chosen.candidates}
    created = 0
    for verdict in verdicts:
        if not verdict.is_match or verdict.coverage < 1:
            continue
        try:
            # The suggestion is attributed to the person who started the run (audit log).
            with audit_operation(
                "mapping.ai_suggest", actor_id=run.created_by_id, run_id=str(run.id)
            ):
                await mapping.create_link(
                    db,
                    objective,
                    by_code[verdict.code],
                    source=MappingSource.AI,
                    coverage=verdict.coverage,
                    depth_match=verdict.depth_match,
                    rationale=verdict.rationale,
                    evidence_quote=verdict.evidence_quote,
                    confidence=verdict.confidence,
                    ai_run=run,
                )
        except (ConflictError, InvalidRequestError):
            continue
        created += 1
    return created


async def execute_run(
    db: AsyncSession,
    settings: Settings,
    run_id: uuid.UUID,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    embedder: EmbeddingProvider | None = None,
    redis: Redis | None = None,
    after_objective: Callable[[], Awaitable[None]] | None = None,
) -> AIRun:
    """Do a queued run. Never raises for the ordinary ways a run ends; the run row says how.

    ``after_objective`` is awaited after each objective (the job commits there, so progress
    is visible while the run goes on).
    """
    run = await db.get(AIRun, run_id)
    if run is None or run.status != AIRunStatus.QUEUED or run.type != AIRunType.MAPPING:
        raise InvalidRequestError("This run cannot be started.")
    run.status = AIRunStatus.RUNNING
    run.started_at = datetime.now(UTC)
    await db.flush()
    if after_objective:
        await after_objective()

    framework = await db.get(Framework, uuid.UUID(run.scope["framework_id"]))
    module_id = run.scope.get("module_id")
    objectives = await scope_objectives(
        db, uuid.UUID(run.scope["version_id"]), uuid.UUID(module_id) if module_id else None
    )
    k = int(run.parameters.get("top_k", DEFAULT_K))
    in_row = 0
    attempts = 0
    notes: list[str] = []
    try:
        if framework is None or framework.is_deleted:
            raise InvalidRequestError("The framework was deleted.")
        for objective in objectives:
            await db.refresh(run)
            if run.status == AIRunStatus.CANCELLED:
                break
            try:
                made = await _map_objective(
                    db, settings, run, objective, framework, k, transport, embedder, redis
                )
                if made is not None:
                    attempts += 1
                    run.links_created += made
                    in_row = 0
            except PersonalDataRefusedError:
                attempts += 1
                run.failed_items += 1
                notes.append(
                    "some objectives were skipped because they may hold personal information"
                )
            except AIBudgetExceededError as exc:
                run.status = AIRunStatus.BUDGET_EXCEEDED
                run.error_message = str(exc)[:1000]
                break
            except AIRefusedError as exc:
                run.status = AIRunStatus.FAILED
                run.error_message = str(exc)[:1000]
                break
            except (ProviderError, InvalidAnswer) as exc:
                attempts += 1
                run.failed_items += 1
                in_row = in_row + 1 if isinstance(exc, ProviderError) else 0
                if in_row >= MAX_IN_ROW:
                    run.status = AIRunStatus.FAILED
                    run.error_message = "The AI provider failed several times in a row."
                    run.done_items += 1
                    break
            run.done_items += 1
            await db.flush()
            if after_objective:
                await after_objective()
    except AIError as exc:
        run.status = AIRunStatus.FAILED
        run.error_message = str(exc)[:1000]
    except InvalidRequestError as exc:
        run.status = AIRunStatus.FAILED
        run.error_message = str(exc)[:1000]
    except Exception as exc:
        logger.error("mapping_run_crashed", run_id=str(run.id), error=type(exc).__name__)
        run.status = AIRunStatus.FAILED
        run.error_message = "The run stopped because of an unexpected error."

    if run.status == AIRunStatus.RUNNING:
        everything_failed = attempts > 0 and run.failed_items >= attempts
        run.status = AIRunStatus.FAILED if everything_failed else AIRunStatus.SUCCEEDED
        if everything_failed:
            run.error_message = "No objective could be mapped."
        elif notes:
            run.error_message = "; ".join(dict.fromkeys(notes))
    run.finished_at = run.finished_at or datetime.now(UTC)
    await db.flush()
    if after_objective:
        await after_objective()
    logger.info(
        "mapping_run_finished",
        run_id=str(run.id),
        status=run.status.value,
        total=run.total_items,
        done=run.done_items,
        failed=run.failed_items,
        links=run.links_created,
    )
    return run
