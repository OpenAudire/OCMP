"""Emails about sign-in and passwords."""

import asyncio
import uuid

import dramatiq

import app.core.broker  # noqa: F401  (sets the broker before actors are declared)
from app.core.config import get_settings
from app.core.logging import get_logger
from app.jobs.resources import job_resources
from app.services.email import get_email_sender
from app.services.password_reset import password_changed_email, send_reset_email
from app.services.users import get_active_user

logger = get_logger(__name__)


async def _send_password_reset(email: str) -> None:
    settings = get_settings()
    async with job_resources(settings) as (db, redis):
        await send_reset_email(db, redis, settings, get_email_sender(settings), email)


async def _send_password_changed(user_id: str) -> None:
    settings = get_settings()
    sender = get_email_sender(settings)
    if sender is None:
        logger.warning("password_changed_notice_not_sent", reason="smtp_not_configured")
        return
    async with job_resources(settings) as (db, _redis):
        user = await get_active_user(db, uuid.UUID(user_id))
        if user is None:
            return
        await asyncio.to_thread(sender.send, password_changed_email(settings, user))
    logger.info("password_changed_notice_sent", user_id=user_id)


# No retries: a retry would issue another token; the user can simply ask again.
@dramatiq.actor(max_retries=0)
def send_password_reset(email: str) -> None:
    """Email a reset link if the address belongs to an eligible account."""
    asyncio.run(_send_password_reset(email))


@dramatiq.actor(max_retries=3)
def send_password_changed_notice(user_id: str) -> None:
    """Tell a user their password was changed."""
    asyncio.run(_send_password_changed(user_id))
