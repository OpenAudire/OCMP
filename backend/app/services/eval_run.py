"""Running the evaluation harness (Slice 1.19, ADR 048).

An evaluation run asks the AI to map the objectives of a gold set, exactly as a mapping run
would (same shortlist, same prompt, same checks), but **saves no link and changes no objective**:
it keeps the answers on the run so the figures can be worked out afterwards (``eval_metrics``).
Two things are switched off so that earlier decisions cannot leak into the measurement: the
shortlist ignores links the objective already has and the precedent boost, and the prompt gets
no examples of earlier reviewer decisions. The figures are therefore a *cold start*: a
programme with reviewed links will do somewhat better in practice.

Gold objectives are matched by wording to the live objectives of a curriculum version (the
shortlist needs the objective's stored vector). A gold objective with no match is counted as
not found and left out of the figures.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import httpx
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import prompts
from app.ai.embeddings import EmbeddingProvider
from app.ai.errors import (
    AIBudgetExceededError,
    AIError,
    AIRefusedError,
    PersonalDataRefusedError,
    ProviderError,
)
from app.ai.mapping_answer import InvalidAnswer
from app.core.config import Settings
from app.core.logging import get_logger
from app.models import (
    AIRun,
    CurriculumVersion,
    EvalRun,
    Framework,
    FrameworkItem,
    GoldCase,
    GoldLink,
    GoldSet,
    Objective,
)
from app.models.framework import FrameworkStatus
from app.models.mapping import AIRunStatus, AIRunType
from app.services import ai_gateway
from app.services.ai_mapping import (
    ACTIVE,
    MAX_IN_ROW,
    MAX_K,
    MIN_K,
    _ask,
    expire_stale_runs,
    scope_objectives,
    states_depth,
    taxonomy_verbs,
)
from app.services.authorization import ConflictError, InvalidRequestError
from app.services.eval_gold import normal
from app.services.eval_metrics import CaseResult, GoldRow, Match
from app.services.mapping_shortlist import DEFAULT_K, shortlist

logger = get_logger(__name__)


async def start_eval(
    db: AsyncSession,
    settings: Settings,
    *,
    actor_id: uuid.UUID,
    gold_set: GoldSet,
    version: CurriculumVersion,
    top_k: int = DEFAULT_K,
) -> tuple[EvalRun, AIRun]:
    """Check what can be checked now and queue a run (the caller queues the job).

    Raises:
        ConflictError: If an evaluation of this gold set is queued or running.
        InvalidRequestError: For a framework not in use, a shortlist size out of range, or a
            gold set with no objectives.
        AIRefusedError: If AI is off, restricted or not set up.
    """
    framework = await db.get(Framework, gold_set.framework_id)
    if framework is None or framework.is_deleted or framework.status == FrameworkStatus.DRAFT:
        raise InvalidRequestError("The gold set's framework is not in use.")
    if not MIN_K <= top_k <= MAX_K:
        raise InvalidRequestError(f"The shortlist size must be between {MIN_K} and {MAX_K}.")
    total = (
        await db.scalar(
            select(func.count()).select_from(GoldCase).where(GoldCase.gold_set_id == gold_set.id)
        )
    ) or 0
    if total == 0:
        raise InvalidRequestError("The gold set has no objectives.")
    await expire_stale_runs(db)
    for other in await db.scalars(
        select(AIRun).where(AIRun.type == AIRunType.EVALUATION, AIRun.status.in_(ACTIVE))
    ):
        if other.scope.get("gold_set_id") == str(gold_set.id):
            raise ConflictError("An evaluation of this gold set is already going.")
    provider, model = await ai_gateway.ensure_ready(db, settings)
    run = AIRun(
        type=AIRunType.EVALUATION,
        status=AIRunStatus.QUEUED,
        provider=provider,
        model=model,
        prompt_version=f"{prompts.MAPPING.name}:{prompts.MAPPING.version}",
        parameters={"top_k": top_k},
        scope={
            "gold_set_id": str(gold_set.id),
            "version_id": str(version.id),
            "framework_id": str(framework.id),
        },
        total_items=total,
        created_by_id=actor_id,
    )
    db.add(run)
    await db.flush()
    evaluation = EvalRun(
        gold_set_id=gold_set.id,
        ai_run_id=run.id,
        version_id=version.id,
        top_k=top_k,
        created_by_id=actor_id,
    )
    db.add(evaluation)
    await db.flush()
    return evaluation, run


async def _parent_chains(db: AsyncSession, framework_id: uuid.UUID) -> dict[str, tuple[str, ...]]:
    """For every item code of the framework: the codes of its parent, grandparent and so on."""
    rows = (
        await db.execute(
            select(FrameworkItem.id, FrameworkItem.code, FrameworkItem.parent_id).where(
                FrameworkItem.framework_id == framework_id
            )
        )
    ).all()
    code_of = {item_id: code for item_id, code, _ in rows}
    parent_of = {item_id: parent for item_id, _, parent in rows}
    chains: dict[str, tuple[str, ...]] = {}
    for item_id, code in code_of.items():
        chain: list[str] = []
        current = parent_of.get(item_id)
        while current is not None and current in code_of and len(chain) < 20:
            chain.append(code_of[current])
            current = parent_of.get(current)
        chains[code] = tuple(chain)
    return chains


async def execute_eval(
    db: AsyncSession,
    settings: Settings,
    eval_id: uuid.UUID,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    embedder: EmbeddingProvider | None = None,
    redis: Redis | None = None,
    after_case: Callable[[], Awaitable[None]] | None = None,
) -> EvalRun:
    """Do a queued evaluation. Never raises for the ordinary ways a run ends; the AI run row
    says how it ended. ``after_case`` is awaited after each gold objective (the job commits)."""
    evaluation = await db.get(EvalRun, eval_id)
    run = await db.get(AIRun, evaluation.ai_run_id) if evaluation else None
    if (
        evaluation is None
        or run is None
        or run.status != AIRunStatus.QUEUED
        or run.type != AIRunType.EVALUATION
    ):
        raise InvalidRequestError("This evaluation cannot be started.")
    run.status = AIRunStatus.RUNNING
    run.started_at = datetime.now(UTC)
    await db.flush()
    if after_case:
        await after_case()

    framework = await db.get(Framework, uuid.UUID(run.scope["framework_id"]))
    in_row = attempts = 0
    results: list[dict[str, Any]] = []
    not_found = 0
    try:
        if framework is None or framework.is_deleted:
            raise InvalidRequestError("The framework was deleted.")
        cases = list(
            await db.scalars(
                select(GoldCase)
                .where(GoldCase.gold_set_id == evaluation.gold_set_id)
                .order_by(GoldCase.position)
            )
        )
        objectives: dict[str, Objective] = {}
        for candidate in await scope_objectives(db, evaluation.version_id, None):
            objectives.setdefault(normal(candidate.text), candidate)
        verbs = await taxonomy_verbs(db)
        chains = await _parent_chains(db, framework.id)
        for case in cases:
            await db.refresh(run)
            if run.status != AIRunStatus.RUNNING:
                break
            objective = objectives.get(normal(case.objective_text))
            entry: dict[str, Any] = {"case_id": str(case.id), "found": objective is not None}
            if objective is None:
                not_found += 1
                run.done_items += 1
                results.append(entry)
                continue
            try:
                chosen = await shortlist(
                    db,
                    settings,
                    objective,
                    framework.id,
                    k=evaluation.top_k,
                    provider=embedder,
                    redis=redis,
                    include_linked=True,
                    use_precedent=False,
                )
                entry["shortlist"] = [c.item.code for c in chosen.candidates]
                entry["ancestors"] = {
                    code: list(chains.get(code, ())) for code in entry["shortlist"]
                }
                if not chosen.candidates:
                    entry["matches"] = []
                else:
                    depthless = frozenset(
                        c.item.code for c in chosen.candidates if not states_depth(c.item, verbs)
                    )
                    verdicts = await _ask(
                        db,
                        settings,
                        run,
                        objective,
                        framework,
                        chosen.candidates,
                        "",
                        transport,
                        depthless,
                    )
                    entry["matches"] = [
                        {
                            "code": v.code,
                            "coverage": v.coverage,
                            "depth": v.depth_match.value,
                            "confidence": float(v.confidence),
                        }
                        for v in verdicts
                        if v.is_match and v.code in entry["shortlist"]
                    ]
                if chosen.candidates:
                    # Only an objective that was really asked about counts for or against the run.
                    attempts += 1
                    in_row = 0
                    run.links_created += len(entry["matches"])
            except PersonalDataRefusedError:
                attempts += 1
                run.failed_items += 1
                entry["failed"] = True
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
                entry["failed"] = True
                in_row = in_row + 1 if isinstance(exc, ProviderError) else 0
                if in_row >= MAX_IN_ROW:
                    run.status = AIRunStatus.FAILED
                    run.error_message = "The AI provider failed several times in a row."
                    run.done_items += 1
                    results.append(entry)
                    break
            results.append(entry)
            run.done_items += 1
            evaluation.results = list(results)
            await db.flush()
            if after_case:
                await after_case()
    except AIError as exc:
        run.status = AIRunStatus.FAILED
        run.error_message = str(exc)[:1000]
    except InvalidRequestError as exc:
        run.status = AIRunStatus.FAILED
        run.error_message = str(exc)[:1000]
    except Exception as exc:
        logger.error("evaluation_crashed", run_id=str(run.id), error=type(exc).__name__)
        run.status = AIRunStatus.FAILED
        run.error_message = "The evaluation stopped because of an unexpected error."

    evaluation.results = list(results)
    evaluation.not_found = not_found
    if run.status == AIRunStatus.RUNNING:
        everything_failed = attempts > 0 and run.failed_items >= attempts
        run.status = AIRunStatus.FAILED if everything_failed else AIRunStatus.SUCCEEDED
        if everything_failed:
            run.error_message = "No objective could be answered."
    run.finished_at = run.finished_at or datetime.now(UTC)
    await db.flush()
    if after_case:
        await after_case()
    logger.info(
        "evaluation_finished",
        run_id=str(run.id),
        status=run.status.value,
        total=run.total_items,
        failed=run.failed_items,
        not_found=not_found,
    )
    return evaluation


# --- Reading results ------------------------------------------------------------------------


async def case_results(db: AsyncSession, evaluation: EvalRun) -> list[CaseResult]:
    """The stored answers joined with the gold rows as they are now (found objectives only)."""
    gold: dict[str, list[GoldRow]] = {}
    rows = await db.execute(
        select(GoldLink.case_id, GoldLink.item_code, GoldLink.coverage, GoldLink.depth)
        .join(GoldCase, GoldCase.id == GoldLink.case_id)
        .where(GoldCase.gold_set_id == evaluation.gold_set_id)
    )
    for case_id, code, coverage, depth in rows:
        gold.setdefault(str(case_id), []).append(
            GoldRow(code, coverage, depth.value if depth else None)
        )
    results = []
    for entry in evaluation.results:
        if not entry.get("found", False):
            continue
        results.append(
            CaseResult(
                case_id=entry["case_id"],
                gold=tuple(gold.get(entry["case_id"], ())),
                shortlist=tuple(entry.get("shortlist", ())),
                matches=tuple(
                    Match(m["code"], m["coverage"], m.get("depth"), m.get("confidence"))
                    for m in entry.get("matches", ())
                ),
                ancestors={k: tuple(v) for k, v in entry.get("ancestors", {}).items()},
                failed=bool(entry.get("failed", False)),
            )
        )
    return results
