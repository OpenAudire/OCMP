"""Dramatiq worker entry point.

Run with: ``dramatiq app.worker``
"""

import dramatiq
from dramatiq.brokers.redis import RedisBroker

from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging

settings = get_settings()
setup_logging(log_level=settings.log_level, json_logs=not settings.debug)

broker = RedisBroker(url=str(settings.redis_url))  # type: ignore[no-untyped-call]
dramatiq.set_broker(broker)

logger = get_logger(__name__)


@dramatiq.actor
def ping() -> None:
    """No-op actor used to verify the worker is consuming jobs."""
    logger.info("Worker ping received")
