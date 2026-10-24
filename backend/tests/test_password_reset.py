"""Tests for the password reset service and its background jobs."""

import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from fakeredis import FakeAsyncRedis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import PasswordPolicyError, verify_password
from app.jobs import auth_emails
from app.models import User
from app.services.password_reset import (
    InvalidResetTokenError,
    reset_password,
    send_reset_email,
)
from app.services.users import change_password, create_local_user
from tests.factories import UserFactory
from tests.fakes import FakeEmailSender

EMAIL = "lecturer@example.org"
PASSWORD = "a long enough passphrase"
NEW_PASSWORD = "a brand new passphrase"


@pytest.fixture
async def user(db_session: AsyncSession, test_settings: Settings) -> User:
    return await create_local_user(
        db_session, test_settings, email=EMAIL, display_name="Demo Lecturer", password=PASSWORD
    )


@pytest.fixture
def sender() -> FakeEmailSender:
    return FakeEmailSender()


def token_from(sender: FakeEmailSender) -> str:
    match = re.search(r"/reset-password#token=([\w-]+)", sender.sent[-1].body)
    assert match, sender.sent[-1].body
    return match.group(1)


async def request_reset(
    db: AsyncSession,
    redis: FakeAsyncRedis,
    settings: Settings,
    sender: FakeEmailSender | None,
    email: str = EMAIL,
) -> bool:
    return await send_reset_email(db, redis, settings, sender, email)


class TestSendResetEmail:
    async def test_sends_link_to_account_owner(
        self,
        db_session: AsyncSession,
        redis_client: FakeAsyncRedis,
        test_settings: Settings,
        sender: FakeEmailSender,
        user: User,
    ) -> None:
        assert await request_reset(db_session, redis_client, test_settings, sender)

        (message,) = sender.sent
        assert message.to == EMAIL
        assert "Demo Lecturer" in message.body
        assert "60 minutes" in message.body
        # Token travels in the URL fragment, never the query string.
        assert f"{test_settings.public_url}/reset-password#token=" in message.body
        assert "?" not in message.body

    async def test_redis_holds_only_the_token_hash(
        self,
        db_session: AsyncSession,
        redis_client: FakeAsyncRedis,
        test_settings: Settings,
        sender: FakeEmailSender,
        user: User,
    ) -> None:
        await request_reset(db_session, redis_client, test_settings, sender)
        token = token_from(sender)

        keys = await redis_client.keys("ocmp:password-reset*")
        values = [await redis_client.get(k) for k in keys]
        assert keys
        assert not any(token in k for k in keys)
        assert not any(token in (v or "") for v in values)

    async def test_link_expires_after_configured_time(
        self,
        db_session: AsyncSession,
        redis_client: FakeAsyncRedis,
        test_settings: Settings,
        sender: FakeEmailSender,
        user: User,
    ) -> None:
        await request_reset(db_session, redis_client, test_settings, sender)

        (key,) = await redis_client.keys("ocmp:password-reset:*")
        assert 3500 < await redis_client.ttl(key) <= 3600

    @pytest.mark.parametrize("email", ["nobody@example.org", "not-an-email"])
    async def test_unknown_address_gets_nothing(
        self,
        db_session: AsyncSession,
        redis_client: FakeAsyncRedis,
        test_settings: Settings,
        sender: FakeEmailSender,
        user: User,
        email: str,
    ) -> None:
        assert not await request_reset(db_session, redis_client, test_settings, sender, email)
        assert sender.sent == []

    async def test_address_is_case_insensitive(
        self,
        db_session: AsyncSession,
        redis_client: FakeAsyncRedis,
        test_settings: Settings,
        sender: FakeEmailSender,
        user: User,
    ) -> None:
        assert await request_reset(
            db_session, redis_client, test_settings, sender, "LECTURER@example.org"
        )

    async def test_inactive_and_deleted_accounts_get_nothing(
        self,
        db_session: AsyncSession,
        redis_client: FakeAsyncRedis,
        test_settings: Settings,
        sender: FakeEmailSender,
        user: User,
    ) -> None:
        user.is_active = False
        await db_session.flush()
        assert not await request_reset(db_session, redis_client, test_settings, sender)

        user.is_active = True
        user.soft_delete()
        await db_session.flush()
        assert not await request_reset(db_session, redis_client, test_settings, sender)
        assert sender.sent == []

    async def test_sso_only_account_gets_nothing(
        self,
        db_session: AsyncSession,
        redis_client: FakeAsyncRedis,
        test_settings: Settings,
        sender: FakeEmailSender,
    ) -> None:
        sso_user = UserFactory(password_hash=None)
        db_session.add(sso_user)
        await db_session.flush()

        assert not await request_reset(
            db_session, redis_client, test_settings, sender, sso_user.email
        )

    async def test_without_smtp_nothing_is_sent(
        self,
        db_session: AsyncSession,
        redis_client: FakeAsyncRedis,
        test_settings: Settings,
        user: User,
    ) -> None:
        assert not await request_reset(db_session, redis_client, test_settings, None)
        assert await redis_client.keys("ocmp:password-reset*") == []

    async def test_emails_per_account_are_capped(
        self,
        db_session: AsyncSession,
        redis_client: FakeAsyncRedis,
        test_settings: Settings,
        sender: FakeEmailSender,
        user: User,
    ) -> None:
        for _ in range(test_settings.password_reset_per_account_per_hour + 2):
            await request_reset(db_session, redis_client, test_settings, sender)

        assert len(sender.sent) == test_settings.password_reset_per_account_per_hour


class TestResetPassword:
    async def issue(
        self,
        db: AsyncSession,
        redis: FakeAsyncRedis,
        settings: Settings,
        sender: FakeEmailSender,
    ) -> str:
        await request_reset(db, redis, settings, sender)
        return token_from(sender)

    async def test_sets_new_password(
        self,
        db_session: AsyncSession,
        redis_client: FakeAsyncRedis,
        test_settings: Settings,
        sender: FakeEmailSender,
        user: User,
    ) -> None:
        token = await self.issue(db_session, redis_client, test_settings, sender)

        result = await reset_password(
            db_session, redis_client, test_settings, token=token, new_password=NEW_PASSWORD
        )

        assert result is user
        assert user.password_hash is not None
        assert verify_password(user.password_hash, NEW_PASSWORD)
        assert await redis_client.keys("ocmp:password-reset*") == []

    async def test_token_is_single_use(
        self,
        db_session: AsyncSession,
        redis_client: FakeAsyncRedis,
        test_settings: Settings,
        sender: FakeEmailSender,
        user: User,
    ) -> None:
        token = await self.issue(db_session, redis_client, test_settings, sender)
        await reset_password(
            db_session, redis_client, test_settings, token=token, new_password=NEW_PASSWORD
        )

        with pytest.raises(InvalidResetTokenError):
            await reset_password(
                db_session, redis_client, test_settings, token=token, new_password=PASSWORD
            )

    async def test_unknown_or_expired_token(
        self,
        db_session: AsyncSession,
        redis_client: FakeAsyncRedis,
        test_settings: Settings,
        sender: FakeEmailSender,
        user: User,
    ) -> None:
        token = await self.issue(db_session, redis_client, test_settings, sender)
        await redis_client.flushall()  # as if the TTL had passed

        for candidate in (token, "made-up-token"):
            with pytest.raises(InvalidResetTokenError):
                await reset_password(
                    db_session,
                    redis_client,
                    test_settings,
                    token=candidate,
                    new_password=NEW_PASSWORD,
                )

    async def test_newer_link_replaces_older(
        self,
        db_session: AsyncSession,
        redis_client: FakeAsyncRedis,
        test_settings: Settings,
        sender: FakeEmailSender,
        user: User,
    ) -> None:
        first = await self.issue(db_session, redis_client, test_settings, sender)
        second = await self.issue(db_session, redis_client, test_settings, sender)

        with pytest.raises(InvalidResetTokenError):
            await reset_password(
                db_session, redis_client, test_settings, token=first, new_password=NEW_PASSWORD
            )
        await reset_password(
            db_session, redis_client, test_settings, token=second, new_password=NEW_PASSWORD
        )

    async def test_password_change_invalidates_link(
        self,
        db_session: AsyncSession,
        redis_client: FakeAsyncRedis,
        test_settings: Settings,
        sender: FakeEmailSender,
        user: User,
    ) -> None:
        token = await self.issue(db_session, redis_client, test_settings, sender)
        await change_password(
            db_session,
            test_settings,
            user,
            current_password=PASSWORD,
            new_password="changed some other way",
        )

        with pytest.raises(InvalidResetTokenError):
            await reset_password(
                db_session, redis_client, test_settings, token=token, new_password=NEW_PASSWORD
            )

    async def test_deactivated_account_cannot_use_link(
        self,
        db_session: AsyncSession,
        redis_client: FakeAsyncRedis,
        test_settings: Settings,
        sender: FakeEmailSender,
        user: User,
    ) -> None:
        token = await self.issue(db_session, redis_client, test_settings, sender)
        user.is_active = False
        await db_session.flush()

        with pytest.raises(InvalidResetTokenError):
            await reset_password(
                db_session, redis_client, test_settings, token=token, new_password=NEW_PASSWORD
            )

    async def test_rejected_password_does_not_use_up_link(
        self,
        db_session: AsyncSession,
        redis_client: FakeAsyncRedis,
        test_settings: Settings,
        sender: FakeEmailSender,
        user: User,
    ) -> None:
        token = await self.issue(db_session, redis_client, test_settings, sender)

        with pytest.raises(PasswordPolicyError):
            await reset_password(
                db_session, redis_client, test_settings, token=token, new_password="short"
            )
        await reset_password(
            db_session, redis_client, test_settings, token=token, new_password=NEW_PASSWORD
        )


class TestJobs:
    """The Dramatiq job bodies, with their connections replaced by test ones."""

    @pytest.fixture
    def job_env(
        self,
        monkeypatch: pytest.MonkeyPatch,
        db_session: AsyncSession,
        redis_client: FakeAsyncRedis,
        test_settings: Settings,
        sender: FakeEmailSender,
    ) -> None:
        @asynccontextmanager
        async def fake_resources(
            _settings: Settings,
        ) -> AsyncIterator[tuple[AsyncSession, FakeAsyncRedis]]:
            yield db_session, redis_client

        monkeypatch.setattr(auth_emails, "job_resources", fake_resources)
        monkeypatch.setattr(auth_emails, "get_settings", lambda: test_settings)
        monkeypatch.setattr(auth_emails, "get_email_sender", lambda _s: sender)

    @pytest.mark.usefixtures("job_env")
    async def test_password_reset_job_sends_link(self, sender: FakeEmailSender, user: User) -> None:
        await auth_emails._send_password_reset("lecturer@example.org")

        assert "reset-password#token=" in sender.sent[0].body

    @pytest.mark.usefixtures("job_env")
    async def test_password_changed_job_notifies_user(
        self, sender: FakeEmailSender, user: User
    ) -> None:
        await auth_emails._send_password_changed(str(user.id))

        (message,) = sender.sent
        assert message.to == EMAIL
        assert "was just changed" in message.body

    @pytest.mark.usefixtures("job_env")
    async def test_password_changed_job_skips_missing_user(self, sender: FakeEmailSender) -> None:
        await auth_emails._send_password_changed("00000000-0000-0000-0000-000000000000")

        assert sender.sent == []

    async def test_password_changed_job_without_smtp(
        self, monkeypatch: pytest.MonkeyPatch, test_settings: Settings
    ) -> None:
        monkeypatch.setattr(auth_emails, "get_settings", lambda: test_settings)

        # No SMTP in test settings: returns without opening any connection.
        await auth_emails._send_password_changed("00000000-0000-0000-0000-000000000000")


async def test_job_resources_connect_and_clean_up(
    migrated_database: str, test_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """job_resources opens a real database session and closes everything afterwards."""
    from sqlalchemy import text

    from app.jobs import resources

    redis = FakeAsyncRedis(decode_responses=True)
    monkeypatch.setattr(resources.Redis, "from_url", lambda *a, **k: redis)
    settings = test_settings.model_copy(update={"database_url": migrated_database})

    async with resources.job_resources(settings) as (db, job_redis):
        assert (await db.execute(text("SELECT 1"))).scalar_one() == 1
        assert job_redis is redis


async def test_concurrent_use_of_link_succeeds_once(
    db_session: AsyncSession,
    redis_client: FakeAsyncRedis,
    test_settings: Settings,
    sender: FakeEmailSender,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If another request consumed the token between lookup and use, this one fails."""
    await request_reset(db_session, redis_client, test_settings, sender)
    token = token_from(sender)

    async def already_consumed(_key: str) -> None:
        return None

    monkeypatch.setattr(redis_client, "getdel", already_consumed)

    with pytest.raises(InvalidResetTokenError):
        await reset_password(
            db_session, redis_client, test_settings, token=token, new_password=NEW_PASSWORD
        )
    assert user.password_hash is not None
    assert verify_password(user.password_hash, PASSWORD)
