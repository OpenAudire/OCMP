# ADR 001: Background Job Library

## Status

Accepted

## Context

OCMP needs a background job system for:
- AI mapping runs (potentially long-running)
- LMS sync operations
- Report generation
- Email sending
- Embedding computation

The project brief suggests either Celery or Dramatiq with Redis as the broker.

## Decision

We will use **Dramatiq** with Redis as the message broker.

## Rationale

1. **Simpler architecture**: Dramatiq has fewer moving parts than Celery (no separate beat scheduler needed for most use cases)
2. **Better defaults**: Dramatiq's defaults are production-ready out of the box
3. **Native async support**: Better alignment with our FastAPI async codebase
4. **Smaller dependency footprint**: Fewer transitive dependencies
5. **Clear API**: More straightforward API for defining and enqueueing tasks
6. **Redis-native**: Works well with Redis, which we already need for caching

## Consequences

- Workers are started with `dramatiq` command
- Periodic tasks will use APScheduler or dramatiq-crontab
- Task results stored in Redis with configurable TTL
- Monitoring via dramatiq-dashboard or custom admin UI
