"""Background job that runs an evaluation of a gold set (Slice 1.19, ADR 048)."""

import asyncio
import uuid

import dramatiq

import app.core.broker  # noqa: F401  (sets the broker before actors are declared)
from app.ai.embeddings import get_embedding_provider
from app.ai.errors import ProviderError
from app.core.config import Settings, get_settings
from app.jobs.resources import job_resources
from app.models import EvalRun
from app.services.eval_run import execute_eval


async def run_evaluation_job(settings: Settings, eval_id: str) -> EvalRun:
    """The body of ``run_evaluation``: commits after each gold objective so a screen sees
    progress."""
    async with job_resources(settings) as (db, redis):
        try:
            embedder = get_embedding_provider(settings)
        except ProviderError:
            embedder = None
        return await execute_eval(
            db,
            settings,
            uuid.UUID(eval_id),
            embedder=embedder,
            redis=redis,
            after_case=db.commit,
        )


# No retries: a retry would pay the provider again for objectives already answered.
@dramatiq.actor(max_retries=0, time_limit=6 * 60 * 60 * 1000)
def run_evaluation(eval_id: str) -> None:
    """Ask the AI to map the objectives of a queued evaluation."""
    asyncio.run(run_evaluation_job(get_settings(), eval_id))
