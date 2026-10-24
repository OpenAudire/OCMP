"""Dramatiq broker shared by the API (which enqueues jobs) and the worker.

Importing this module sets the global broker, which Dramatiq binds actors to
when they are declared, so every module that declares actors imports it first.
The Redis connection is opened lazily, on the first enqueue.
"""

import dramatiq
from dramatiq.brokers.redis import RedisBroker

from app.core.config import get_settings

broker = RedisBroker(url=str(get_settings().redis_url))  # type: ignore[no-untyped-call]
dramatiq.set_broker(broker)
