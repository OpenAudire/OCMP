"""Background job that reads a study guide with the AI (Slice 1.18, ADR 047)."""

import asyncio
import uuid

import dramatiq

import app.core.broker  # noqa: F401  (sets the broker before actors are declared)
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.jobs.resources import job_resources
from app.models import AIRun
from app.services.study_guide_extraction import execute_extraction

logger = get_logger(__name__)


async def run_study_guide_job(settings: Settings, run_id: str) -> AIRun:
    """The body of ``run_study_guide``: commits after each piece so the screen sees progress."""
    async with job_resources(settings) as (db, redis):
        return await execute_extraction(
            db, settings, redis, uuid.UUID(run_id), after_piece=db.commit
        )


# No retries: a retry would call a paid provider again for pieces already read.
@dramatiq.actor(max_retries=0, time_limit=60 * 60 * 1000)
def run_study_guide(run_id: str) -> None:
    """Read the pieces of an uploaded study guide and propose objectives from them."""
    asyncio.run(run_study_guide_job(get_settings(), run_id))
