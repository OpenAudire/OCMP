"""Sign-in with an external identity provider, independent of protocol.

OIDC uses this now; SAML (phase 2) will produce the same ``ExternalIdentity``.

Accounts are matched on (issuer, subject) only. An SSO sign-in is never
attached to an existing account because the email addresses match: providers
do not guarantee email claims are verified or stable, so matching on them
would let anyone who can set an email address at the provider take over the
local account with that address. Linking existing accounts is an
administrator action.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.models import User, UserIdentity
from app.services.users import InvalidEmailError, normalise_email


@dataclass(frozen=True)
class ExternalIdentity:
    """A person as asserted by a trusted identity provider."""

    protocol: str
    issuer: str
    subject: str
    # Contact details only; never used to identify the person.
    email: str | None
    display_name: str | None


class SSOSignInError(Exception):
    """SSO sign-in cannot complete. ``code`` is safe to show to the user."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code


async def _find_identity(db: AsyncSession, identity: ExternalIdentity) -> UserIdentity | None:
    result = await db.execute(
        select(UserIdentity)
        .where(UserIdentity.issuer == identity.issuer, UserIdentity.subject == identity.subject)
        .options(selectinload(UserIdentity.user))
    )
    return result.scalar_one_or_none()


async def _email_taken(db: AsyncSession, email: str) -> bool:
    # Includes soft-deleted accounts, which still hold their address.
    result = await db.execute(select(User.id).where(func.lower(User.email) == email.lower()))
    return result.first() is not None


async def sign_in_external(
    db: AsyncSession, settings: Settings, identity: ExternalIdentity
) -> User:
    """Return the user for an external identity, creating the account if allowed.

    Raises:
        SSOSignInError: With code ``account_disabled``, ``not_provisioned``,
            ``no_email`` or ``account_exists``.
    """
    now = datetime.now(UTC)
    linked = await _find_identity(db, identity)
    if linked is not None:
        user = linked.user
        if not user.is_active or user.is_deleted:
            raise SSOSignInError("account_disabled", "This account is disabled.")
        linked.last_login_at = now
        user.last_login_at = now
        await db.flush()
        return user

    if not settings.oidc_auto_provision:
        raise SSOSignInError("not_provisioned", "No account is set up for this sign-in.")
    if not identity.email:
        raise SSOSignInError("no_email", "The provider did not supply an email address.")
    try:
        email = normalise_email(identity.email)
    except InvalidEmailError as exc:
        raise SSOSignInError("no_email", "The provider supplied an invalid email.") from exc
    if await _email_taken(db, email):
        raise SSOSignInError(
            "account_exists",
            "An account with this email address already exists; an administrator must link it.",
        )

    display_name = (identity.display_name or "").strip() or email.split("@", 1)[0]
    user = User(
        email=email,
        display_name=display_name[:255],
        password_hash=None,
        last_login_at=now,
    )
    db.add(user)
    await db.flush()
    db.add(
        UserIdentity(
            user_id=user.id,
            protocol=identity.protocol,
            issuer=identity.issuer,
            subject=identity.subject,
            last_login_at=now,
        )
    )
    await db.flush()
    return user
