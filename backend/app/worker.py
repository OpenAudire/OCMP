"""Dramatiq worker entry point.

Run with: ``dramatiq app.worker``
"""

import dramatiq

import app.core.broker
import app.jobs.auth_emails  # noqa: F401  (registers its actors with the worker)
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging

settings = get_settings()
setup_logging(log_level=settings.log_level, json_logs=not settings.debug)

logger = get_logger(__name__)


@dramatiq.actor
def ping() -> None:
    """No-op actor used to verify the worker is consuming jobs."""
    logger.info("Worker ping received")
