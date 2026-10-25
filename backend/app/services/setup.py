"""First-run setup: create the institution and the first platform admin.

On a fresh install the setup endpoint works without signing in, so it is
protected by a setup token only the server operator can see: it is derived
from ``SECRET_KEY``, printed in the API log while setup is pending, and shown
by ``python -m app.cli setup-token``. Setup is possible only while no
institution exists; an advisory lock makes concurrent attempts safe.
"""

import base64
import hashlib
import hmac
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.permissions import ScopeType
from app.core.profiles import Profile
from app.models import Institution, User
from app.services.audit import audit_operation
from app.services.authorization import (
    AuthorizationError,
    ConflictError,
    ScopeRef,
    assign_role,
    get_role,
    sync_system_roles,
)
from app.services.institution_settings import InstitutionSettings
from app.services.users import create_local_user

# Any constant: serialises setup attempts across API processes.
_SETUP_LOCK_ID = 0x0C3F_5E70


def setup_token(settings: Settings) -> str:
    """The setup token for this server, e.g. ``K7QX-2M4D-PB9W-H3TZ`` (80 bits)."""
    digest = hmac.new(settings.secret_key.encode(), b"ocmp-setup", hashlib.sha256).digest()
    code = base64.b32encode(digest[:10]).decode()
    return "-".join(code[i : i + 4] for i in range(0, 16, 4))


def _normalise_token(token: str) -> str:
    return token.strip().upper().replace(" ", "").replace("-", "")


def token_matches(settings: Settings, token: str) -> bool:
    """Compare a submitted token in constant time (dashes, spaces and case ignored)."""
    expected = _normalise_token(setup_token(settings))
    return hmac.compare_digest(expected.encode(), _normalise_token(token).encode())


async def setup_needed(db: AsyncSession) -> bool:
    """Whether the instance still needs first-run setup (no institution yet)."""
    exists = await db.scalar(select(Institution.id).where(Institution.deleted_at.is_(None)))
    return exists is None


@dataclass(frozen=True)
class SetupRequest:
    token: str
    institution_name: str
    institution_short_code: str
    country: str
    health_profile: bool
    admin_display_name: str
    admin_email: str
    admin_password: str


async def complete_setup(db: AsyncSession, settings: Settings, request: SetupRequest) -> User:
    """Create the institution and its first platform admin.

    Raises:
        AuthorizationError: If the setup token is wrong.
        ConflictError: If setup was already completed.
        InvalidEmailError, PasswordPolicyError: For an invalid admin account.
    """
    if not token_matches(settings, request.token):
        raise AuthorizationError("The setup token is not correct.")

    # Only one setup at a time; re-check inside the lock.
    await db.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": _SETUP_LOCK_ID})
    if not await setup_needed(db):
        raise ConflictError("OCMP has already been set up.")

    # All or nothing: a rejected admin account must not leave an institution behind.
    async with db.begin_nested():
        with audit_operation("setup.complete"):
            await sync_system_roles(db)
            profiles = {Profile.CORE} | ({Profile.HEALTH} if request.health_profile else set())
            institution = Institution(
                name=request.institution_name.strip(),
                short_code=request.institution_short_code.strip().upper(),
                country=request.country.strip().upper(),
                settings={
                    "profiles": InstitutionSettings(profiles=frozenset(profiles)).section(
                        "profiles"
                    )
                },
            )
            db.add(institution)
            admin = await create_local_user(
                db,
                settings,
                email=request.admin_email,
                display_name=request.admin_display_name,
                password=request.admin_password,
            )
            role = await get_role(db, key="platform_admin")
            assert role is not None
            await assign_role(db, None, user=admin, role=role, scope=ScopeRef(ScopeType.INSTANCE))
    return admin
