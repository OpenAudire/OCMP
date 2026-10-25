"""Administration commands.

    python -m app.cli sync-roles
    python -m app.cli create-admin --email admin@example.org --name "Admin"
    python -m app.cli purge-ai-content [--days N]
    python -m app.cli purge-audit-log [--days N]
    python -m app.cli setup-token

``create-admin`` reads the password from OCMP_ADMIN_PASSWORD or prompts for it.
If the account already exists (e.g. created by SSO), it is made a platform
admin without changing its password. This is the bootstrap and recovery path
until the first-run setup wizard exists.
"""

import argparse
import asyncio
import getpass
import os
import sys

from app.core import database
from app.core.config import get_settings
from app.core.permissions import ScopeType
from app.core.security import PasswordPolicyError
from app.services.ai_runs import purge_ai_call_content
from app.services.audit import purge_audit_log
from app.services.authorization import (
    ConflictError,
    ScopeRef,
    assign_role,
    get_role,
    sync_system_roles,
)
from app.services.setup import setup_needed, setup_token
from app.services.users import InvalidEmailError, create_local_user, get_user_by_email


async def _sync_roles() -> int:
    async with database.session_scope() as db:
        roles = await sync_system_roles(db)
    print(f"System roles synced: {', '.join(r.key for r in roles)}")  # noqa: T201
    return 0


async def _create_admin(email: str, name: str) -> int:
    settings = get_settings()
    async with database.session_scope() as db:
        await sync_system_roles(db)
        role = await get_role(db, key="platform_admin")
        assert role is not None
        user = await get_user_by_email(db, email)
        if user is None:
            password = os.environ.get("OCMP_ADMIN_PASSWORD") or getpass.getpass("Password: ")
            try:
                user = await create_local_user(
                    db, settings, email=email, display_name=name, password=password
                )
            except (InvalidEmailError, PasswordPolicyError) as exc:
                print(f"Error: {exc}", file=sys.stderr)  # noqa: T201
                return 1
        try:
            await assign_role(db, None, user=user, role=role, scope=ScopeRef(ScopeType.INSTANCE))
        except ConflictError:
            print("User is already a platform admin.")  # noqa: T201
            return 0
    print(f"Platform admin ready: {user.id}")  # noqa: T201
    return 0


async def _purge_ai_content(days: int) -> int:
    async with database.session_scope() as db:
        purged = await purge_ai_call_content(db, older_than_days=days)
    print(f"Cleared stored prompts and responses of {purged} AI calls older than {days} days.")  # noqa: T201
    return 0


async def _purge_audit_log(days: int) -> int:
    if days <= 0:
        print("Audit log retention is off (keep forever); nothing deleted.")  # noqa: T201
        return 0
    async with database.session_scope() as db:
        deleted = await purge_audit_log(db, older_than_days=days)
    print(f"Deleted {deleted} audit log entries older than {days} days.")  # noqa: T201
    return 0


async def _setup_token() -> int:
    async with database.session_scope() as db:
        pending = await setup_needed(db)
    if not pending:
        print("Setup is already complete; the setup token is no longer accepted.")  # noqa: T201
        return 0
    print(f"Setup token: {setup_token(get_settings())}")  # noqa: T201
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("sync-roles", help="Create or update the built-in roles.")
    admin = commands.add_parser("create-admin", help="Create or promote a platform admin.")
    admin.add_argument("--email", required=True)
    admin.add_argument("--name", default="Platform admin")
    purge = commands.add_parser(
        "purge-ai-content", help="Clear stored AI prompts and responses past retention."
    )
    purge.add_argument("--days", type=int, default=None, help="Default: AI_CALL_RETENTION_DAYS.")
    commands.add_parser("setup-token", help="Show the first-run setup token.")
    audit_purge = commands.add_parser(
        "purge-audit-log", help="Delete audit log entries past retention."
    )
    audit_purge.add_argument(
        "--days", type=int, default=None, help="Default: AUDIT_LOG_RETENTION_DAYS."
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    database.init_database(settings)

    async def run() -> int:
        try:
            if args.command == "sync-roles":
                return await _sync_roles()
            if args.command == "setup-token":
                return await _setup_token()
            if args.command == "purge-audit-log":
                days = args.days if args.days is not None else settings.audit_log_retention_days
                return await _purge_audit_log(days)
            if args.command == "purge-ai-content":
                days = args.days if args.days is not None else settings.ai_call_retention_days
                return await _purge_ai_content(days)
            return await _create_admin(args.email, args.name)
        finally:
            await database.close_database()

    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
