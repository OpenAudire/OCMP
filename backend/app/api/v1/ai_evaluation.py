"""The evaluation harness: gold sets, evaluation runs and their figures (Slice 1.19, ADR 048).

All of it needs ``settings.manage`` (the people who set up AI), and a run is limited to curriculum
versions the user can see (ADR 027). A gold set is imported from the Excel template (with a dry
run that lists every problem), a run asks the AI about the gold set's objectives and saves no
link, and the figures are worked out from the stored answers at any threshold.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import SettingsDep, require_permission
from app.api.v1.curriculum import Access
from app.core.database import DbSession
from app.core.permissions import Permission
from app.jobs.evaluation import run_evaluation
from app.models import AIRun, EvalRun, Framework, GoldCase, GoldLink, GoldSet, User
from app.models.mapping import AIRunStatus, AIRunType
from app.services import eval_gold, eval_metrics, eval_run
from app.services.ai_mapping import ACTIVE, MAX_K, MIN_K, cancel_run, expire_stale_runs
from app.services.audit import audit_operation
from app.services.curriculum_read import visible_version
from app.services.mapping_shortlist import DEFAULT_K

router = APIRouter(prefix="/ai/evaluation", tags=["ai-evaluation"])

SettingsManager = Annotated[User, Depends(require_permission(Permission.SETTINGS_MANAGE))]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_DISAGREEMENTS = 100


def _not_found(what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found.")


class ProblemRead(BaseModel):
    row: int | None
    message: str


class GoldSetRead(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    framework_id: uuid.UUID
    framework_name: str
    is_demo: bool
    objectives: int
    mappings: int
    without_mapping: int
    created_at: datetime


class GoldPreview(BaseModel):
    objectives: int
    mappings: int
    without_mapping: int
    problems: list[ProblemRead]
    saved: GoldSetRead | None = None


class EvalRunCreate(BaseModel):
    gold_set_id: uuid.UUID
    version_id: uuid.UUID
    top_k: int = Field(default=DEFAULT_K, ge=MIN_K, le=MAX_K)


class EvalRunRead(BaseModel):
    id: uuid.UUID
    gold_set_id: uuid.UUID
    gold_set_name: str
    version_id: uuid.UUID
    status: AIRunStatus
    prompt_version: str
    provider: str
    model: str
    top_k: int
    total_items: int
    done_items: int
    failed_items: int
    not_found: int
    input_tokens: int
    output_tokens: int
    estimated_cost: Decimal
    error_message: str | None
    created_at: datetime
    finished_at: datetime | None
    # The figures at the minimum coverage asked for (list and detail).
    scores: dict[str, Any] | None = None


class EvalDetail(EvalRunRead):
    min_coverage: int
    prefer_specific: bool
    by_min_coverage: list[dict[str, Any]]
    bulk_accept: list[dict[str, Any]]
    disagreements: list[dict[str, Any]]


async def _gold_read(db: DbSession, gold: GoldSet) -> GoldSetRead:
    framework = await db.get(Framework, gold.framework_id)
    objectives = (
        await db.scalar(
            select(func.count()).select_from(GoldCase).where(GoldCase.gold_set_id == gold.id)
        )
        or 0
    )
    mappings = (
        await db.scalar(
            select(func.count())
            .select_from(GoldLink)
            .join(GoldCase, GoldCase.id == GoldLink.case_id)
            .where(GoldCase.gold_set_id == gold.id, GoldLink.coverage >= 1)
        )
        or 0
    )
    with_mapping = (
        await db.scalar(
            select(func.count(func.distinct(GoldLink.case_id)))
            .join(GoldCase, GoldCase.id == GoldLink.case_id)
            .where(GoldCase.gold_set_id == gold.id, GoldLink.coverage >= 1)
        )
        or 0
    )
    return GoldSetRead(
        id=gold.id,
        name=gold.name,
        description=gold.description,
        framework_id=gold.framework_id,
        framework_name=framework.name if framework else "",
        is_demo=gold.is_demo,
        objectives=objectives,
        mappings=mappings,
        without_mapping=objectives - with_mapping,
        created_at=gold.created_at,
    )


async def _gold(db: DbSession, gold_set_id: uuid.UUID) -> GoldSet:
    gold = await db.get(GoldSet, gold_set_id)
    if gold is None or gold.is_deleted:
        raise _not_found("Gold set")
    return gold


@router.get("/gold-template")
async def gold_template(
    _: SettingsManager, db: DbSession, framework_id: uuid.UUID | None = None
) -> Response:
    """The empty Excel workbook to fill in by hand (with a framework: its item codes)."""
    framework = None
    if framework_id is not None:
        framework = await db.get(Framework, framework_id)
        if framework is None or framework.is_deleted:
            raise _not_found("Framework")
    content = await eval_gold.build_template(db, framework)
    return Response(
        content,
        media_type=XLSX,
        headers={"Content-Disposition": 'attachment; filename="gold-set-template.xlsx"'},
    )


@router.get("/gold-sets", response_model=list[GoldSetRead])
async def list_gold_sets(_: SettingsManager, db: DbSession) -> list[GoldSetRead]:
    sets = await db.scalars(
        select(GoldSet).where(GoldSet.deleted_at.is_(None)).order_by(GoldSet.created_at.desc())
    )
    return [await _gold_read(db, gold) for gold in sets]


@router.post("/gold-sets", response_model=GoldPreview)
async def import_gold_set(
    actor: SettingsManager,
    db: DbSession,
    response: Response,
    name: Annotated[str, Form()],
    framework_id: Annotated[uuid.UUID, Form()],
    file: Annotated[UploadFile, File()],
    description: Annotated[str, Form()] = "",
    dry_run: Annotated[bool, Form()] = False,
) -> GoldPreview:
    """Read a filled-in template. With ``dry_run`` nothing is saved: the answer lists the counts
    and every problem with its row. Otherwise a sound file is saved (201) and a file with problems
    is refused (422) with the same list."""
    framework = await db.get(Framework, framework_id)
    if framework is None or framework.is_deleted:
        raise _not_found("Framework")
    content = await file.read(eval_gold.MAX_FILE_BYTES + 1)
    parsed = await eval_gold.preview(db, framework, content)
    preview = GoldPreview(
        objectives=len(parsed.cases),
        mappings=parsed.links,
        without_mapping=parsed.empty_cases,
        problems=[ProblemRead(row=p.row, message=p.message) for p in parsed.problems],
    )
    if dry_run:
        return preview
    if parsed.problems:
        response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        return preview
    gold = await eval_gold.save_gold_set(
        db,
        actor_id=actor.id,
        name=name,
        description=description,
        framework=framework,
        parsed=parsed,
    )
    response.status_code = status.HTTP_201_CREATED
    preview.saved = await _gold_read(db, gold)
    return preview


@router.get("/gold-sets/{gold_set_id}/export")
async def export_gold_set(gold_set_id: uuid.UUID, _: SettingsManager, db: DbSession) -> Response:
    gold = await _gold(db, gold_set_id)
    return Response(
        await eval_gold.export_gold_set(db, gold),
        media_type=XLSX,
        headers={"Content-Disposition": 'attachment; filename="gold-set.xlsx"'},
    )


@router.delete("/gold-sets/{gold_set_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_gold_set(gold_set_id: uuid.UUID, actor: SettingsManager, db: DbSession) -> None:
    """Remove a gold set from the list (its evaluation runs go with it)."""
    gold = await _gold(db, gold_set_id)
    with audit_operation("eval.gold_set_delete", actor_id=actor.id):
        gold.soft_delete()
        await db.flush()


def _run_read(
    evaluation: EvalRun,
    run: AIRun,
    gold_name: str,
    scores: dict[str, Any] | None = None,
) -> EvalRunRead:
    return EvalRunRead(
        id=evaluation.id,
        gold_set_id=evaluation.gold_set_id,
        gold_set_name=gold_name,
        version_id=evaluation.version_id,
        status=run.status,
        prompt_version=run.prompt_version,
        provider=run.provider,
        model=run.model,
        top_k=evaluation.top_k,
        total_items=run.total_items,
        done_items=run.done_items,
        failed_items=run.failed_items,
        not_found=evaluation.not_found,
        input_tokens=run.input_tokens,
        output_tokens=run.output_tokens,
        estimated_cost=run.estimated_cost,
        error_message=run.error_message,
        created_at=evaluation.created_at,
        finished_at=run.finished_at,
        scores=scores,
    )


@router.post("/runs", response_model=EvalRunRead, status_code=status.HTTP_202_ACCEPTED)
async def start_evaluation(
    body: EvalRunCreate,
    actor: SettingsManager,
    access: Access,
    db: DbSession,
    settings: SettingsDep,
) -> EvalRunRead:
    """Queue an evaluation of a gold set on the objectives of a curriculum version."""
    gold = await _gold(db, body.gold_set_id)
    visible = await visible_version(db, access, body.version_id)
    if visible is None:
        raise _not_found("Curriculum version")
    with audit_operation("eval.run_start", actor_id=actor.id):
        evaluation, run = await eval_run.start_eval(
            db,
            settings,
            actor_id=actor.id,
            gold_set=gold,
            version=visible.version,
            top_k=body.top_k,
        )
    run_evaluation.send(str(evaluation.id))
    return _run_read(evaluation, run, gold.name)


@router.get("/runs", response_model=list[EvalRunRead])
async def list_evaluations(
    _: SettingsManager,
    db: DbSession,
    gold_set_id: uuid.UUID | None = None,
    min_coverage: Annotated[int, Query(ge=1, le=5)] = 1,
    prefer_specific: bool = True,
) -> list[EvalRunRead]:
    """Evaluation runs, newest first, each with its figures at the minimum coverage asked for:
    the table that compares prompt versions and models."""
    await expire_stale_runs(db)
    query = select(EvalRun).order_by(EvalRun.created_at.desc()).limit(100)
    if gold_set_id is not None:
        query = query.where(EvalRun.gold_set_id == gold_set_id)
    rows = []
    for evaluation in await db.scalars(query):
        run = await db.get(AIRun, evaluation.ai_run_id)
        gold = await db.get(GoldSet, evaluation.gold_set_id)
        if run is None or gold is None or gold.is_deleted:
            continue
        scores = None
        if run.status not in ACTIVE:
            cases = await eval_run.case_results(db, evaluation)
            scores = eval_metrics.scores_dict(
                eval_metrics.score(
                    cases, min_coverage=min_coverage, prefer_specific=prefer_specific
                )
            )
        rows.append(_run_read(evaluation, run, gold.name, scores))
    return rows


async def _evaluation(db: DbSession, eval_id: uuid.UUID) -> tuple[EvalRun, AIRun, GoldSet]:
    evaluation = await db.get(EvalRun, eval_id)
    run = await db.get(AIRun, evaluation.ai_run_id) if evaluation else None
    gold = await db.get(GoldSet, evaluation.gold_set_id) if evaluation else None
    if evaluation is None or run is None or gold is None or run.type != AIRunType.EVALUATION:
        raise _not_found("Evaluation")
    return evaluation, run, gold


@router.get("/runs/{eval_id}", response_model=EvalDetail)
async def get_evaluation(
    eval_id: uuid.UUID,
    _: SettingsManager,
    db: DbSession,
    min_coverage: Annotated[int, Query(ge=1, le=5)] = 1,
    prefer_specific: bool = True,
) -> EvalDetail:
    """One run with its figures at the chosen minimum coverage, the figures at every minimum
    coverage, what bulk accept would do at each floor, and the objectives where the AI and the
    gold set disagree."""
    evaluation, run, gold = await _evaluation(db, eval_id)
    await expire_stale_runs(db)
    await db.refresh(run)
    cases = await eval_run.case_results(db, evaluation)
    texts = {
        str(c.id): c.objective_text
        for c in await db.scalars(select(GoldCase).where(GoldCase.gold_set_id == gold.id))
    }
    disagreements = []
    for case in cases:
        if case.failed:
            continue
        diff = eval_metrics.case_differences(
            case, min_coverage=min_coverage, prefer_specific=prefer_specific
        )
        if diff["only_ai"] or diff["only_gold"]:
            disagreements.append(
                {"case_id": case.case_id, "objective": texts.get(case.case_id, ""), **diff}
            )
    base = _run_read(
        evaluation,
        run,
        gold.name,
        eval_metrics.scores_dict(
            eval_metrics.score(cases, min_coverage=min_coverage, prefer_specific=prefer_specific)
        ),
    )
    return EvalDetail(
        **base.model_dump(),
        min_coverage=min_coverage,
        prefer_specific=prefer_specific,
        by_min_coverage=eval_metrics.sweep(cases, prefer_specific=prefer_specific),
        bulk_accept=eval_metrics.bulk_sweep(
            cases, min_coverage=min_coverage, prefer_specific=prefer_specific
        ),
        disagreements=disagreements[:MAX_DISAGREEMENTS],
    )


@router.post("/runs/{eval_id}/cancel", response_model=EvalRunRead)
async def cancel_evaluation(eval_id: uuid.UUID, _: SettingsManager, db: DbSession) -> EvalRunRead:
    evaluation, run, gold = await _evaluation(db, eval_id)
    if run.status in ACTIVE:
        await cancel_run(db, run)
    return _run_read(evaluation, run, gold.name)
