"""Tests for the administration commands (run against the real test database)."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import Executable, Row, delete, select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app import cli
from app.core.config import Settings
from app.models import Role, RoleAssignment, User

EMAIL = "cli.admin@example.org"


async def _query(url: str, statement: Executable) -> list[Row[Any]]:
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            result = await conn.execute(statement)
            return list(result.all()) if result.returns_rows else []
    finally:
        await engine.dispose()


@pytest.fixture
def cli_settings(
    migrated_database: str, test_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> Iterator[str]:
    settings = test_settings.model_copy(update={"database_url": migrated_database})
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    yield migrated_database
    # These commands commit, so remove what they created.
    asyncio.run(_query(migrated_database, delete(User).where(User.email == EMAIL)))


def test_sync_roles(cli_settings: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["sync-roles"]) == 0

    keys = {row[0] for row in asyncio.run(_query(cli_settings, select(Role.key)))}
    assert {"platform_admin", "student"} <= keys
    assert "System roles synced" in capsys.readouterr().out


def test_create_admin_then_rerun(
    cli_settings: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("OCMP_ADMIN_PASSWORD", "a long enough passphrase")

    assert cli.main(["create-admin", "--email", EMAIL, "--name", "CLI Admin"]) == 0
    assert "Platform admin ready" in capsys.readouterr().out

    rows = asyncio.run(
        _query(
            cli_settings,
            select(Role.key)
            .join(RoleAssignment, RoleAssignment.role_id == Role.id)
            .join(User, User.id == RoleAssignment.user_id)
            .where(User.email == EMAIL),
        )
    )
    assert [r[0] for r in rows] == ["platform_admin"]

    assert cli.main(["create-admin", "--email", EMAIL]) == 0
    assert "already a platform admin" in capsys.readouterr().out


def test_create_admin_rejects_weak_password(
    cli_settings: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("OCMP_ADMIN_PASSWORD", "short")

    assert cli.main(["create-admin", "--email", EMAIL]) == 1
    assert "at least 12" in capsys.readouterr().err


def test_purge_ai_content(cli_settings: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["purge-ai-content", "--days", "30"]) == 0

    assert "older than 30 days" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("days", "message"), [("0", "retention is off"), ("3650", "older than 3650 days")]
)
def test_purge_audit_log(
    cli_settings: str, capsys: pytest.CaptureFixture[str], days: str, message: str
) -> None:
    assert cli.main(["purge-audit-log", "--days", days]) == 0

    assert message in capsys.readouterr().out


def test_setup_token(cli_settings: str, capsys: pytest.CaptureFixture[str]) -> None:
    from app.services.setup import setup_token

    assert cli.main(["setup-token"]) == 0

    out = capsys.readouterr().out
    # The test database has no institution, so setup is pending.
    assert setup_token(cli.get_settings()) in out
