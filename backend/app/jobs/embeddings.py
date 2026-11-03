"""Background jobs that embed objectives and framework items (ADR 044)."""

import asyncio
import uuid

import dramatiq
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.core.broker  # noqa: F401  (sets the broker before actors are declared)
from app.ai.embeddings import EmbeddingProvider, get_embedding_provider
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.jobs.resources import job_resources
from app.models import Objective
from app.models.embedding import EmbeddedType
from app.services.embeddings import SyncResult, sweep, sync_embeddings
from app.services.objective_duplicates import refresh_similarities

logger = get_logger(__name__)


class ObjectiveNotFoundYet(Exception):
    """The objective is not visible to the job yet (the saving request may not have
    committed). The job is retried."""


async def embed_one_objective(
    db: AsyncSession, provider: EmbeddingProvider, objective_id: uuid.UUID
) -> None:
    """Embed one objective and refresh its near-duplicate pairs.

    Raises:
        ObjectiveNotFoundYet: If the objective is not visible yet.
        ProviderError: If the embeddings server cannot be used.
    """
    exists = await db.scalar(select(Objective.id).where(Objective.id == objective_id))
    if exists is None:
        raise ObjectiveNotFoundYet(str(objective_id))
    await sync_embeddings(db, provider, EmbeddedType.OBJECTIVE, ids=[objective_id])
    await refresh_similarities(db, objective_id)


async def run_embed_objective(settings: Settings, objective_id: str) -> None:
    """The body of ``embed_objective``: nothing while embeddings are off."""
    if not settings.embeddings_local:
        return
    async with job_resources(settings) as (db, _redis):
        await embed_one_objective(db, get_embedding_provider(settings), uuid.UUID(objective_id))


async def run_embed_pending(settings: Settings, entity_type: str) -> SyncResult:
    """The body of ``embed_pending``: nothing while embeddings are off."""
    if not settings.embeddings_local:
        return SyncResult()
    async with job_resources(settings) as (db, _redis):
        return await sweep(db, get_embedding_provider(settings), EmbeddedType(entity_type))


# A save may reach the job before it commits, and the server may be restarting: retry for a
# while, with growing pauses.
@dramatiq.actor(max_retries=6, min_backoff=5_000, max_backoff=300_000)
def embed_objective(objective_id: str) -> None:
    """Embed one objective and refresh its near-duplicate pairs."""
    asyncio.run(run_embed_objective(get_settings(), objective_id))


@dramatiq.actor(max_retries=3, min_backoff=30_000, max_backoff=600_000)
def embed_pending(entity_type: str) -> None:
    """Embed everything of a type that is new or changed, and drop what is gone."""
    asyncio.run(run_embed_pending(get_settings(), entity_type))


def enqueue_objective(settings: Settings, objective_id: uuid.UUID) -> None:
    """Queue the embedding of an objective after a save; nothing while embeddings are off."""
    if settings.embeddings_local:
        embed_objective.send(str(objective_id))


def enqueue_pending(settings: Settings, entity_type: EmbeddedType) -> None:
    """Queue a sweep of a type (after a copy forward or a framework import)."""
    if settings.embeddings_local:
        embed_pending.send(entity_type.value)
