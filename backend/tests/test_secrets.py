"""Tests for the encryption of stored secrets (ADR 041)."""

import pytest

from app.core.config import Settings
from app.core.secrets import (
    PREFIX,
    SecretBox,
    SecretsNotConfiguredError,
    SecretUnreadableError,
    derive_key,
    key_id,
    new_key,
)

SECRET_KEY = "test-secret-key-that-is-at-least-32-characters-long"
DB = "postgresql+asyncpg://user:pass@localhost:5432/db"


def settings(**kwargs: object) -> Settings:
    options: dict[str, object] = {"environment": "development", **kwargs}
    return Settings(secret_key=SECRET_KEY, database_url=DB, **options)  # type: ignore[arg-type]


class TestSecretBox:
    def test_round_trip_and_format(self) -> None:
        box = SecretBox([new_key()])

        stored = box.encrypt("sk-not-a-real-key")

        assert stored.startswith(f"{PREFIX}:{box.primary_id}:")
        assert "sk-not-a-real-key" not in stored
        assert box.decrypt(stored) == "sk-not-a-real-key"

    def test_two_encryptions_differ(self) -> None:
        box = SecretBox([new_key()])
        assert box.encrypt("same") != box.encrypt("same")

    def test_key_id_does_not_reveal_the_key(self) -> None:
        key = new_key()
        assert key not in key_id(key)
        assert len(key_id(key)) == 8

    def test_old_key_still_reads_and_needs_rotation(self) -> None:
        old, new = new_key(), new_key()
        stored = SecretBox([old]).encrypt("value")

        box = SecretBox([new, old])

        assert box.decrypt(stored) == "value"
        assert box.needs_rotation(stored) is True
        assert box.needs_rotation(box.encrypt("value")) is False

    def test_missing_key_gives_a_clear_error_without_the_value(self) -> None:
        stored = SecretBox([new_key()]).encrypt("value")

        with pytest.raises(SecretUnreadableError, match="not configured") as error:
            SecretBox([new_key()]).decrypt(stored)

        assert "value" not in str(error.value).replace("the value", "")

    def test_tampered_value_is_refused(self) -> None:
        box = SecretBox([new_key()])
        stored = box.encrypt("value")
        head, _, token = stored.rpartition(":")

        with pytest.raises(SecretUnreadableError):
            box.decrypt(f"{head}:{token[:-4]}AAAA")

    @pytest.mark.parametrize("stored", ["", "plain", "other:abcd:xyz", "ocmp1:onlytwo"])
    def test_unknown_formats_are_refused(self, stored: str) -> None:
        box = SecretBox([new_key()])
        with pytest.raises(SecretUnreadableError):
            box.decrypt(stored)
        assert box.needs_rotation(stored) is True

    def test_needs_at_least_one_key(self) -> None:
        with pytest.raises(ValueError, match="At least one"):
            SecretBox([])


class TestFromSettings:
    def test_works_with_only_secret_key(self) -> None:
        box = SecretBox.from_settings(settings())

        assert box.decrypt(box.encrypt("value")) == "value"
        assert box.primary_id == key_id(derive_key(SECRET_KEY))

    def test_derived_key_depends_on_secret_key(self) -> None:
        assert derive_key(SECRET_KEY) != derive_key(SECRET_KEY + "x")
        assert derive_key(SECRET_KEY) == derive_key(SECRET_KEY)

    def test_configured_key_is_newest_and_derived_stays_readable(self) -> None:
        before = SecretBox.from_settings(settings()).encrypt("value")
        configured = new_key()

        box = SecretBox.from_settings(settings(secrets_encryption_keys=[configured]))

        assert box.primary_id == key_id(configured)
        assert box.decrypt(before) == "value"
        assert box.needs_rotation(before) is True

    def test_changing_secret_key_without_a_configured_key_loses_the_secret(self) -> None:
        stored = SecretBox.from_settings(settings()).encrypt("value")
        other = Settings(
            secret_key="a-different-secret-key-of-at-least-32-chars",
            database_url=DB,
        )

        with pytest.raises(SecretUnreadableError):
            SecretBox.from_settings(other).decrypt(stored)


class TestConfiguredKeyValidation:
    def test_accepts_comma_separated_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        first, second = new_key(), new_key()
        monkeypatch.setenv("SECRETS_ENCRYPTION_KEYS", f"{first}, {second}")

        loaded = Settings(_env_file=None, secret_key=SECRET_KEY, database_url=DB)  # type: ignore[call-arg]

        assert loaded.secrets_encryption_keys == [first, second]

    def test_rejects_a_bad_key_without_echoing_it(self) -> None:
        with pytest.raises(ValueError, match="entry 1") as error:
            settings(secrets_encryption_keys=["not-a-key"])

        assert "not-a-key" not in str(error.value)


class TestProductionWithoutAnOwnKey:
    def test_nothing_new_is_sealed_but_old_values_stay_readable(self) -> None:
        stored = SecretBox.from_settings(settings()).encrypt("value")

        box = SecretBox.from_settings(settings(environment="production"))

        assert box.may_encrypt is False
        with pytest.raises(SecretsNotConfiguredError, match="SECRETS_ENCRYPTION_KEYS"):
            box.encrypt("another")
        assert box.decrypt(stored) == "value"

    def test_with_a_configured_key_production_seals_and_old_values_need_rotation(self) -> None:
        stored = SecretBox.from_settings(settings()).encrypt("value")
        configured = new_key()

        box = SecretBox.from_settings(
            settings(environment="production", secrets_encryption_keys=[configured])
        )

        assert box.may_encrypt is True
        assert box.primary_id == key_id(configured)
        assert box.decrypt(stored) == "value"
        assert box.needs_rotation(stored) is True

    def test_development_keeps_the_derived_key_fallback(self) -> None:
        box = SecretBox.from_settings(settings(environment="development"))

        assert box.may_encrypt is True
        assert box.decrypt(box.encrypt("value")) == "value"
