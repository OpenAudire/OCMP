"""Application configuration using pydantic-settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "OCMP"
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
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list[str]) -> list[str]:
        """Parse CORS origins from comma-separated string or list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    # Email (optional, for password reset)
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_from_name: str = "OCMP"
    smtp_tls: bool = True

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

    @property
    def oidc_configured(self) -> bool:
        """Check if OIDC is configured."""
        return all([
            self.oidc_enabled,
            self.oidc_discovery_url,
            self.oidc_client_id,
            self.oidc_client_secret,
        ])

    # AI providers (optional)
    ai_enabled: bool = False
    ai_anthropic_api_key: str | None = None
    ai_openai_api_key: str | None = None
    ai_openai_base_url: str = "https://api.openai.com/v1"
    ai_ollama_base_url: str | None = None
    ai_monthly_budget_cap: float = 0.0  # 0 = unlimited

    # Embeddings
    embeddings_local: bool = True
    embeddings_local_url: str = "http://embeddings:8080"
    embeddings_openai: bool = False
    embeddings_openai_model: str = "text-embedding-3-small"

    # Connector encryption
    connector_encryption_key: str | None = None

    # Session
    session_expire_hours: int = 24


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
