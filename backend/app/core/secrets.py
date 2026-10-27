"""Encryption of secrets stored in the database (AI provider keys), ADR 041.

Fernet (AES-128-CBC with an HMAC-SHA256 tag, from the ``cryptography`` package) seals each
value. A stored value looks like ``ocmp1:<key id>:<token>``: the key id (a short hash of the
key, not the key) says which configured key sealed it, so rotation can find old values and a
missing key gives a clear message.

Keys come from ``SECRETS_ENCRYPTION_KEYS`` (newest first). A key derived from ``SECRET_KEY``
is always appended as a read-only fallback, so values made before the variable was set stay
readable until rotated. In development the derived key also seals new values; in production
(``ENVIRONMENT=production``, the default) nothing new is sealed until a configured key
exists, because a key derived from ``SECRET_KEY`` would tie every stored secret to it.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import Settings

PREFIX = "ocmp1"
_HKDF_INFO = b"ocmp secret store v1"


class SecretsNotConfiguredError(Exception):
    """Production has no ``SECRETS_ENCRYPTION_KEYS``, so new secrets cannot be stored."""


class SecretUnreadableError(Exception):
    """A stored secret cannot be decrypted with any configured key."""


def new_key() -> str:
    """A new random encryption key (for ``SECRETS_ENCRYPTION_KEYS``)."""
    return Fernet.generate_key().decode()


def derive_key(secret_key: str) -> str:
    """The fallback key derived from ``SECRET_KEY`` (HKDF-SHA256, fixed context string)."""
    raw = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_HKDF_INFO).derive(
        secret_key.encode()
    )
    return base64.urlsafe_b64encode(raw).decode()


def key_id(key: str) -> str:
    """A short public identifier for a key; it does not reveal the key."""
    return hashlib.sha256(b"ocmp key id:" + key.encode()).hexdigest()[:8]


class SecretBox:
    """Encrypts with the newest key, decrypts with any configured key."""

    def __init__(self, keys: list[str], *, may_encrypt: bool = True) -> None:
        if not keys:
            raise ValueError("At least one key is needed.")
        self.may_encrypt = may_encrypt
        self._keys = {key_id(k): Fernet(k.encode()) for k in keys}
        self._primary = key_id(keys[0])

    @classmethod
    def from_settings(cls, settings: Settings) -> "SecretBox":
        """Configured keys first, then the key derived from ``SECRET_KEY`` (read fallback)."""
        keys = [*settings.secrets_encryption_keys, derive_key(settings.secret_key)]
        return cls(
            list(dict.fromkeys(keys)), may_encrypt=not settings.secrets_key_missing_in_production
        )

    @property
    def primary_id(self) -> str:
        return self._primary

    def encrypt(self, plaintext: str) -> str:
        """Seal a value with the newest key.

        Raises:
            SecretsNotConfiguredError: In production without ``SECRETS_ENCRYPTION_KEYS``.
        """
        if not self.may_encrypt:
            raise SecretsNotConfiguredError(
                "Set SECRETS_ENCRYPTION_KEYS on the server before saving an API key "
                "(make one with: python -m app.cli new-encryption-key)."
            )
        token = self._keys[self._primary].encrypt(plaintext.encode()).decode()
        return f"{PREFIX}:{self._primary}:{token}"

    def decrypt(self, stored: str) -> str:
        """Open a stored value.

        Raises:
            SecretUnreadableError: If the format is wrong, the key is not configured, or
                the value was changed. The message never contains the value.
        """
        parts = stored.split(":", 2)
        if len(parts) != 3 or parts[0] != PREFIX:
            raise SecretUnreadableError("The stored secret has an unknown format.")
        fernet = self._keys.get(parts[1])
        if fernet is None:
            raise SecretUnreadableError(
                "The key that encrypted this secret is not configured. Add it back to "
                "SECRETS_ENCRYPTION_KEYS, or enter the secret again."
            )
        try:
            return fernet.decrypt(parts[2].encode()).decode()
        except InvalidToken:
            raise SecretUnreadableError("The stored secret could not be decrypted.") from None

    def needs_rotation(self, stored: str) -> bool:
        """Whether the value was sealed with a key other than the newest one."""
        parts = stored.split(":", 2)
        return len(parts) != 3 or parts[0] != PREFIX or parts[1] != self._primary
