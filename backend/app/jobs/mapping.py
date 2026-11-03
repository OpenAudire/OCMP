"""Background job that runs an AI mapping run (Slice 1.16, ADR 045)."""

import asyncio
import uuid

import dramatiq

import app.core.broker  # noqa: F401  (sets the broker before actors are declared)
from app.ai.embeddings import get_embedding_provider
from app.ai.errors import ProviderError
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.jobs.resources import job_resources
from app.models import AIRun
from app.services.ai_mapping import execute_run

logger = get_logger(__name__)


async def run_ai_mapping_job(settings: Settings, run_id: str) -> AIRun:
    """The body of ``run_ai_mapping``: runs the pipeline and commits after each objective so
    the screen sees progress."""
    async with job_resources(settings) as (db, redis):
        try:
            embedder = get_embedding_provider(settings)
        except ProviderError:
            embedder = None
        return await execute_run(
            db,
            settings,
            uuid.UUID(run_id),
            embedder=embedder,
            redis=redis,
            after_objective=db.commit,
        )


# No retries: a retry would call a paid provider again for objectives already done. The run row
# says how it ended; the person starts another run.
@dramatiq.actor(max_retries=0, time_limit=6 * 60 * 60 * 1000)
def run_ai_mapping(run_id: str) -> None:
    """Map the objectives of a queued run to its framework."""
    asyncio.run(run_ai_mapping_job(get_settings(), run_id))
