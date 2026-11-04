"""Dramatiq worker entry point.

Run with: ``dramatiq app.worker``
"""

import dramatiq

import app.core.broker
import app.jobs.auth_emails
import app.jobs.embeddings
import app.jobs.evaluation
import app.jobs.mapping
import app.jobs.study_guides  # noqa: F401
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging

settings = get_settings()
setup_logging(log_level=settings.log_level, json_logs=not settings.debug)

logger = get_logger(__name__)


@dramatiq.actor
def ping() -> None:
    """No-op actor used to verify the worker is consuming jobs."""
    logger.info("Worker ping received")
