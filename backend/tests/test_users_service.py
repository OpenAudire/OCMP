"""Tests for the user account service."""

import pytest
from argon2 import PasswordHasher
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import PasswordPolicyError, password_needs_rehash, verify_password
from app.services.users import (
    InvalidEmailError,
    UserAlreadyExistsError,
    authenticate,
    change_password,
    create_local_user,
)
from tests.factories import UserFactory

PASSWORD = "a long enough passphrase"


async def make_user(db: AsyncSession, settings: Settings, email: str = "lecturer@example.org"):
    return await create_local_user(
        db, settings, email=email, display_name="  Demo Lecturer ", password=PASSWORD
    )


class TestCreateLocalUser:
    async def test_creates_user_with_hashed_password(
        self, db_session: AsyncSession, test_settings: Settings
    ) -> None:
        user = await make_user(db_session, test_settings)

        assert user.display_name == "Demo Lecturer"
        assert user.password_hash is not None
        assert PASSWORD not in user.password_hash
        assert verify_password(user.password_hash, PASSWORD)

    async def test_normalises_email_domain(
        self, db_session: AsyncSession, test_settings: Settings
    ) -> None:
        user = await make_user(db_session, test_settings, email=" Lecturer@EXAMPLE.org ")

        assert user.email == "Lecturer@example.org"

    async def test_rejects_duplicate_email_ignoring_case(
        self, db_session: AsyncSession, test_settings: Settings
    ) -> None:
        await make_user(db_session, test_settings)

        with pytest.raises(UserAlreadyExistsError):
            await make_user(db_session, test_settings, email="LECTURER@example.org")

    async def test_rejects_invalid_email(
        self, db_session: AsyncSession, test_settings: Settings
    ) -> None:
        with pytest.raises(InvalidEmailError):
            await make_user(db_session, test_settings, email="not-an-email")

    async def test_enforces_password_policy(
        self, db_session: AsyncSession, test_settings: Settings
    ) -> None:
        with pytest.raises(PasswordPolicyError):
            await create_local_user(
                db_session,
                test_settings,
                email="lecturer@example.org",
                display_name="Demo",
                password="short",
            )


class TestAuthenticate:
    async def test_success_records_login_time(
        self, db_session: AsyncSession, test_settings: Settings
    ) -> None:
        user = await make_user(db_session, test_settings)

        result = await authenticate(db_session, "LECTURER@example.org", PASSWORD)

        assert result is user
        assert user.last_login_at is not None

    @pytest.mark.parametrize(
        ("email", "password"),
        [
            ("lecturer@example.org", "wrong passphrase here"),
            ("nobody@example.org", PASSWORD),
        ],
    )
    async def test_wrong_credentials(
        self, db_session: AsyncSession, test_settings: Settings, email: str, password: str
    ) -> None:
        await make_user(db_session, test_settings)

        assert await authenticate(db_session, email, password) is None

    async def test_inactive_user_cannot_sign_in(
        self, db_session: AsyncSession, test_settings: Settings
    ) -> None:
        user = await make_user(db_session, test_settings)
        user.is_active = False

        assert await authenticate(db_session, user.email, PASSWORD) is None

    async def test_deleted_user_cannot_sign_in(
        self, db_session: AsyncSession, test_settings: Settings
    ) -> None:
        user = await make_user(db_session, test_settings)
        user.soft_delete()
        await db_session.flush()

        assert await authenticate(db_session, user.email, PASSWORD) is None

    async def test_sso_only_user_cannot_sign_in_with_password(
        self, db_session: AsyncSession
    ) -> None:
        user = UserFactory(password_hash=None)
        db_session.add(user)
        await db_session.flush()

        assert await authenticate(db_session, user.email, "") is None

    async def test_upgrades_weak_hash(
        self, db_session: AsyncSession, test_settings: Settings
    ) -> None:
        weak = PasswordHasher(time_cost=1, memory_cost=8192).hash(PASSWORD)
        user = UserFactory(password_hash=weak)
        db_session.add(user)
        await db_session.flush()

        await authenticate(db_session, user.email, PASSWORD)

        assert user.password_hash != weak
        assert user.password_hash is not None
        assert not password_needs_rehash(user.password_hash)


class TestChangePassword:
    async def test_changes_password(
        self, db_session: AsyncSession, test_settings: Settings
    ) -> None:
        user = await make_user(db_session, test_settings)

        changed = await change_password(
            db_session,
            test_settings,
            user,
            current_password=PASSWORD,
            new_password="a different passphrase",
        )

        assert changed
        assert await authenticate(db_session, user.email, "a different passphrase") is user
        assert await authenticate(db_session, user.email, PASSWORD) is None

    async def test_wrong_current_password(
        self, db_session: AsyncSession, test_settings: Settings
    ) -> None:
        user = await make_user(db_session, test_settings)

        assert not await change_password(
            db_session,
            test_settings,
            user,
            current_password="not my password",
            new_password="a different passphrase",
        )

    async def test_new_password_must_meet_policy(
        self, db_session: AsyncSession, test_settings: Settings
    ) -> None:
        user = await make_user(db_session, test_settings)

        with pytest.raises(PasswordPolicyError):
            await change_password(
                db_session, test_settings, user, current_password=PASSWORD, new_password="short"
            )
