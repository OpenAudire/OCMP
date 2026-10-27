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


def test_load_demo(
    cli_settings: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Command wiring only; loading itself is tested in test_demo.py (rolled back)."""
    from types import SimpleNamespace

    from app.services.authorization import ConflictError

    calls = []

    async def fake_load_demo(_db: object, **_kw: object) -> SimpleNamespace:
        if len(calls) == 2:
            raise ConflictError("The demo programme BHS-DEMO is already loaded.")
        calls.append(1)
        return SimpleNamespace(
            draft_only=len(calls) == 2,
            draft_year=2027,
            programme=SimpleNamespace(name="BSc Health Sciences (Demo)"),
            modules=3,
            learning_events=20,
            objectives=60,
            objective_links=58,
            framework_items=8,
            mappings=12,
            tag_lists=3,
            office_user_added=False,
        )

    monkeypatch.setattr(cli, "load_demo", fake_load_demo)

    assert cli.main(["load-demo"]) == 0
    out = capsys.readouterr().out
    assert "3 modules, 20 sessions, 60 objectives" in out
    assert "draft for 2027 copied forward" in out
    # An earlier load without the draft gets it added.
    assert cli.main(["load-demo"]) == 0
    assert "Added the 2027 draft" in capsys.readouterr().out
    assert cli.main(["load-demo"]) == 0
    assert "already loaded" in capsys.readouterr().out


def test_clean_orphan_links_is_a_dry_run_unless_applied(
    cli_settings: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Command wiring only; the cleanup itself is tested in test_mapping_live.py."""
    modes = []

    async def fake_clean(_db: object, *, apply: bool) -> int:
        modes.append(apply)
        return 7

    monkeypatch.setattr(cli, "clean_orphan_links", fake_clean)

    assert cli.main(["clean-orphan-links"]) == 0
    assert "7 mapping links belong to deleted objectives. Dry run" in capsys.readouterr().out
    assert cli.main(["clean-orphan-links", "--apply"]) == 0
    assert "Soft-deleted 7 mapping links" in capsys.readouterr().out
    assert modes == [False, True]


def test_new_encryption_key_prints_a_usable_key(capsys: pytest.CaptureFixture[str]) -> None:
    from app.core.secrets import SecretBox

    assert cli.main(["new-encryption-key"]) == 0

    key = capsys.readouterr().out.strip()
    box = SecretBox([key])
    assert box.decrypt(box.encrypt("value")) == "value"


def test_rotate_secrets(
    cli_settings: str,
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import uuid

    from sqlalchemy import insert

    from app.core.secrets import SecretBox, derive_key, new_key
    from app.models import AIProviderConfig, Institution

    old_box = SecretBox([derive_key(test_settings.secret_key)])
    foreign = SecretBox([new_key()]).encrypt("lost")
    institution_id = uuid.uuid4()
    ids = {name: uuid.uuid4() for name in ("old", "lost", "none")}
    asyncio.run(
        _query(
            cli_settings,
            insert(Institution.__table__).values(
                id=institution_id, name="Rotate U", short_code="RU", country="ZA", settings={}
            ),
        )
    )
    rows = [
        (ids["old"], "anthropic", old_box.encrypt("sk-test-not-a-real-key")),
        (ids["lost"], "openai_compatible", foreign),
        (ids["none"], "ollama", None),
    ]
    for config_id, provider, stored in rows:
        asyncio.run(
            _query(
                cli_settings,
                insert(AIProviderConfig.__table__).values(
                    id=config_id,
                    institution_id=institution_id,
                    provider=provider,
                    api_key_encrypted=stored,
                ),
            )
        )
    new = new_key()
    configured = test_settings.model_copy(
        update={"database_url": cli_settings, "secrets_encryption_keys": [new]}
    )
    monkeypatch.setattr(cli, "get_settings", lambda: configured)
    try:
        assert cli.main(["rotate-secrets"]) == 1  # one secret could not be read

        captured = capsys.readouterr()
        assert "Re-encrypted 1 secrets" in captured.out
        assert "1 secrets could not be read" in captured.err
        stored = {
            row[0]: row[1]
            for row in asyncio.run(
                _query(
                    cli_settings,
                    select(AIProviderConfig.id, AIProviderConfig.api_key_encrypted).where(
                        AIProviderConfig.institution_id == institution_id
                    ),
                )
            )
        }
        new_box = SecretBox([new])
        assert new_box.decrypt(stored[ids["old"]]) == "sk-test-not-a-real-key"
        assert not new_box.needs_rotation(stored[ids["old"]])
        assert stored[ids["lost"]] == foreign  # left as it was
        assert stored[ids["none"]] is None

        assert cli.main(["rotate-secrets"]) == 1
        assert "Re-encrypted 0 secrets; 1 already used" in capsys.readouterr().out
    finally:
        asyncio.run(
            _query(
                cli_settings,
                delete(AIProviderConfig).where(AIProviderConfig.institution_id == institution_id),
            )
        )
        asyncio.run(
            _query(cli_settings, delete(Institution).where(Institution.id == institution_id))
        )


def test_rotate_secrets_refuses_in_production_without_its_own_key(
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    production = test_settings.model_copy(
        update={"environment": "production", "secrets_encryption_keys": []}
    )
    monkeypatch.setattr(cli, "get_settings", lambda: production)

    assert cli.main(["rotate-secrets"]) == 1

    assert "SECRETS_ENCRYPTION_KEYS is not set" in capsys.readouterr().err
