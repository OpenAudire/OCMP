"""Application configuration using pydantic-settings."""

import base64
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# A list setting given in the environment as a comma-separated string (not JSON).
CommaSeparatedList = Annotated[list[str], NoDecode]


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        # Errors must never echo a value (keys, passwords) back into logs.
        hide_input_in_errors=True,
    )

    # Application
    # Public address of the site, used to build links in emails.
    public_url: str = "https://localhost"
    app_name: str = "Curriculum in Context"
    app_version: str = "0.1.0"
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # Security
    secret_key: str = Field(..., min_length=32)

    # Database
    database_url: PostgresDsn

    # Redis
    redis_url: RedisDsn = Field(default="redis://localhost:6379/0")  # type: ignore[assignment]

    # CORS
    cors_origins: CommaSeparatedList = Field(default_factory=lambda: ["http://localhost:3000"])

    # Reverse proxies whose X-Forwarded-For header is trusted for the client address:
    # IP addresses, CIDR networks or hostnames (resolved via DNS, e.g. the compose
    # service name). Requests from anywhere else use the connecting address.
    trusted_proxies: CommaSeparatedList = Field(default_factory=lambda: ["caddy"])

    @field_validator("cors_origins", "trusted_proxies", "secrets_encryption_keys", mode="before")
    @classmethod
    def parse_comma_separated(cls, v: str | list[str]) -> list[str]:
        """Parse a list from a comma-separated string or a list."""
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    @field_validator("secrets_encryption_keys", mode="after")
    @classmethod
    def encryption_keys_are_fernet_keys(cls, v: list[str]) -> list[str]:
        """Each key must be a 32 byte URL-safe base64 value; the message never shows the key."""
        for position, key in enumerate(v, start=1):
            try:
                if len(base64.urlsafe_b64decode(key.encode())) != 32:
                    raise ValueError
            except ValueError:
                raise ValueError(
                    f"SECRETS_ENCRYPTION_KEYS entry {position} is not a valid key; "
                    "make one with: python -m app.cli new-encryption-key"
                ) from None
        return v

    # Email (optional, for password reset)
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_from_name: str = "Curriculum in Context"
    smtp_tls: bool = True  # STARTTLS (usually port 587)
    smtp_ssl: bool = False  # implicit TLS (usually port 465); takes precedence over smtp_tls
    smtp_timeout_seconds: float = 10.0

    @property
    def smtp_configured(self) -> bool:
        """Check if SMTP is configured."""
        return all([self.smtp_host, self.smtp_from_email])

    # OIDC (optional)
    oidc_enabled: bool = False
    oidc_provider_name: str = "SSO"
    oidc_discovery_url: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None
    oidc_scopes: str = "openid profile email"
    # Create an account on first SSO sign-in. New accounts have no roles until assigned.
    oidc_auto_provision: bool = True
    oidc_clock_skew_seconds: int = 60  # tolerance for exp/iat in ID tokens
    # Only for testing against a local mock provider; real providers must use HTTPS.
    oidc_allow_insecure_http: bool = False

    @property
    def oidc_redirect_uri(self) -> str:
        """Where the provider sends the browser back; register this with the provider."""
        return f"{self.public_url.rstrip('/')}/api/v1/auth/oidc/callback"

    @property
    def oidc_configured(self) -> bool:
        """Check if OIDC is configured."""
        return all(
            [
                self.oidc_enabled,
                self.oidc_discovery_url,
                self.oidc_client_id,
                self.oidc_client_secret,
            ]
        )

    # AI providers, keys, budgets and local-only mode are set on the admin AI
    # settings screen (ADR 042). Keys are stored encrypted (ADR 041).

    # Keys that encrypt stored secrets (AI provider keys), newest first. Each is a
    # Fernet key (`python -m app.cli new-encryption-key`). Empty: a key is derived from
    # SECRET_KEY. Older keys stay readable until `rotate-secrets` re-encrypts.
    secrets_encryption_keys: CommaSeparatedList = Field(default_factory=list)

    # Stored AI prompts and responses are cleared after this many days
    # (0 = keep). Run records, token counts and links are always kept.
    ai_call_retention_days: int = Field(default=365, ge=0)

    # Audit log entries are deleted after this many days (0 = keep forever).
    audit_log_retention_days: int = Field(default=0, ge=0)

    # Framework pack import: largest upload and most items in one pack (ADR 036).
    pack_max_upload_mb: int = Field(default=10, ge=1, le=200)
    pack_max_items: int = Field(default=20000, ge=1)

    # Embeddings
    # Off by default: the local model is an optional compose profile (ADR 007).
    embeddings_local: bool = False
    embeddings_local_url: str = "http://embeddings:8080"
    embeddings_openai: bool = False
    embeddings_openai_model: str = "text-embedding-3-small"

    # Connector encryption
    connector_encryption_key: str | None = None

    # Session
    session_expire_hours: int = 24  # sliding: renewed on each authenticated request
    session_cookie_name: str = "ocmp_session"
    session_cookie_secure: bool = True  # only disable for local plain-HTTP development
    csrf_cookie_name: str = "ocmp_csrf"
    csrf_header_name: str = "X-CSRF-Token"

    # Password reset
    password_reset_token_minutes: int = 60
    password_reset_per_account_per_hour: int = 3  # emails; extra requests are silently dropped
    password_reset_per_ip: int = 10  # requests per client address per login window

    # Passwords
    password_min_length: int = 12
    password_max_length: int = 256  # bounds hashing cost

    # Login throttling. Per client address: a hard limit on attempts per window.
    # Per account: progressive delays after repeated failures, never a lockout, so
    # nobody can lock another person out by guessing their password.
    login_rate_limit_window_seconds: int = 900
    login_rate_limit_per_ip: int = 20
    login_delay_free_failures: int = 3  # failures before delays start
    login_delay_base_seconds: float = 1.0  # first delay; doubles per further failure
    login_delay_max_seconds: float = 20.0


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
