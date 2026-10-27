"""Tests for configuration module."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


class TestSettings:
    """Tests for Settings class."""

    def test_required_fields(self, monkeypatch: pytest.MonkeyPatch):
        """Test that required fields must be provided."""
        monkeypatch.delenv("SECRET_KEY", raising=False)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        with pytest.raises(ValidationError):
            # Missing required fields should raise validation error
            Settings(_env_file=None)  # type: ignore[call-arg]

    def test_minimal_valid_settings(self):
        """Test minimal valid settings configuration."""
        settings = Settings(
            secret_key="a" * 32,
            database_url="postgresql+asyncpg://user:pass@localhost:5432/db",
        )
        assert settings.secret_key == "a" * 32
        assert str(settings.database_url) == "postgresql+asyncpg://user:pass@localhost:5432/db"

    def test_secret_key_minimum_length(self):
        """Test that secret key must be at least 32 characters."""
        with pytest.raises(ValidationError):
            Settings(
                secret_key="short",
                database_url="postgresql+asyncpg://user:pass@localhost:5432/db",
            )

    def test_cors_origins_from_string(self):
        """Test CORS origins can be parsed from comma-separated string."""
        settings = Settings(
            secret_key="a" * 32,
            database_url="postgresql+asyncpg://user:pass@localhost:5432/db",
            cors_origins="http://localhost:3000, http://localhost:8080",
        )
        assert settings.cors_origins == ["http://localhost:3000", "http://localhost:8080"]

    def test_cors_origins_from_list(self):
        """Test CORS origins can be provided as a list."""
        settings = Settings(
            secret_key="a" * 32,
            database_url="postgresql+asyncpg://user:pass@localhost:5432/db",
            cors_origins=["http://localhost:3000", "http://localhost:8080"],
        )
        assert settings.cors_origins == ["http://localhost:3000", "http://localhost:8080"]

    def test_smtp_configured_property(self):
        """Test smtp_configured property."""
        # Not configured
        settings = Settings(
            secret_key="a" * 32,
            database_url="postgresql+asyncpg://user:pass@localhost:5432/db",
        )
        assert settings.smtp_configured is False

        # Configured
        settings = Settings(
            secret_key="a" * 32,
            database_url="postgresql+asyncpg://user:pass@localhost:5432/db",
            smtp_host="smtp.example.com",
            smtp_from_email="test@example.com",
        )
        assert settings.smtp_configured is True

    def test_oidc_configured_property(self):
        """Test oidc_configured property."""
        # Not configured
        settings = Settings(
            secret_key="a" * 32,
            database_url="postgresql+asyncpg://user:pass@localhost:5432/db",
        )
        assert settings.oidc_configured is False

        # Partially configured (should still be False)
        settings = Settings(
            secret_key="a" * 32,
            database_url="postgresql+asyncpg://user:pass@localhost:5432/db",
            oidc_enabled=True,
            oidc_discovery_url="https://example.com/.well-known/openid-configuration",
        )
        assert settings.oidc_configured is False

        # Fully configured
        settings = Settings(
            secret_key="a" * 32,
            database_url="postgresql+asyncpg://user:pass@localhost:5432/db",
            oidc_enabled=True,
            oidc_discovery_url="https://example.com/.well-known/openid-configuration",
            oidc_client_id="client-id",
            oidc_client_secret="client-secret",
        )
        assert settings.oidc_configured is True

    def test_default_values(self):
        """Test default values are set correctly."""
        settings = Settings(
            secret_key="a" * 32,
            database_url="postgresql+asyncpg://user:pass@localhost:5432/db",
        )
        assert settings.app_name == "Curriculum in Context"
        assert settings.debug is False
        assert settings.log_level == "INFO"
        assert settings.session_expire_hours == 24
        assert settings.secrets_encryption_keys == []
        assert settings.embeddings_local is False


class TestListSettingsFromEnvironment:
    """List settings are given as comma-separated strings in the environment."""

    def test_comma_separated_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CORS_ORIGINS", "https://a.example, https://b.example")
        monkeypatch.setenv("TRUSTED_PROXIES", "caddy,10.0.0.0/8")

        settings = Settings(_env_file=None)  # type: ignore[call-arg]

        assert settings.cors_origins == ["https://a.example", "https://b.example"]
        assert settings.trusted_proxies == ["caddy", "10.0.0.0/8"]

    def test_trusted_proxies_default_to_caddy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TRUSTED_PROXIES", raising=False)

        assert Settings(_env_file=None).trusted_proxies == ["caddy"]  # type: ignore[call-arg]
