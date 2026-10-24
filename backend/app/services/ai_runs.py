"""AI run records and their retention."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AIRunCall


async def purge_ai_call_content(db: AsyncSession, *, older_than_days: int) -> int:
    """Clear stored prompts and responses older than the retention period.

    Runs and calls are kept (they cannot be deleted); only their text goes.
    Token counts, timings, validity and the links made by the run remain.

    Returns:
        The number of calls whose content was cleared.
    """
    if older_than_days <= 0:
        return 0
    now = datetime.now(UTC)
    result = await db.execute(
        update(AIRunCall)
        .where(
            AIRunCall.created_at < now - timedelta(days=older_than_days),
            AIRunCall.content_purged_at.is_(None),
        )
        .values(request={}, response=None, error_message=None, content_purged_at=now)
        .returning(AIRunCall.id)
        .execution_options(synchronize_session="fetch")
    )
    return len(result.all())
