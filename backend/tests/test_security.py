"""Tests for password hashing, password policy and token helpers."""

import pytest
from argon2 import PasswordHasher

from app.core.security import (
    PasswordPolicyError,
    csrf_token_for,
    csrf_token_matches,
    generate_token,
    hash_password,
    hash_token,
    password_needs_rehash,
    validate_password,
    verify_password,
)

SECRET = "x" * 32


class TestPasswordHashing:
    def test_hash_is_argon2id_and_verifies(self) -> None:
        password_hash = hash_password("correct horse battery staple")

        assert password_hash.startswith("$argon2id$")
        assert verify_password(password_hash, "correct horse battery staple")

    def test_wrong_password_does_not_verify(self) -> None:
        password_hash = hash_password("correct horse battery staple")

        assert not verify_password(password_hash, "Correct horse battery staple")

    def test_malformed_hash_does_not_verify(self) -> None:
        assert not verify_password("not-a-hash", "anything")

    def test_hashes_are_salted(self) -> None:
        assert hash_password("same password here") != hash_password("same password here")

    def test_weaker_parameters_need_rehash(self) -> None:
        weak = PasswordHasher(time_cost=1, memory_cost=8192).hash("some password value")

        assert password_needs_rehash(weak)
        assert not password_needs_rehash(hash_password("some password value"))


class TestPasswordPolicy:
    def validate(self, password: str, email: str = "user@example.test") -> None:
        validate_password(password, email=email, min_length=12, max_length=256)

    def test_accepts_long_enough_password(self) -> None:
        self.validate("twelve chars")

    def test_rejects_short_password(self) -> None:
        with pytest.raises(PasswordPolicyError, match="at least 12"):
            self.validate("elevenchars")

    def test_rejects_overlong_password(self) -> None:
        with pytest.raises(PasswordPolicyError, match="at most 256"):
            self.validate("a" * 257)

    def test_rejects_email_as_password(self) -> None:
        with pytest.raises(PasswordPolicyError, match="email"):
            self.validate("Lecturer@Example.test", email="lecturer@example.test")


class TestTokens:
    def test_generated_tokens_are_unique_and_long(self) -> None:
        tokens = {generate_token() for _ in range(100)}

        assert len(tokens) == 100
        assert all(len(t) >= 43 for t in tokens)

    def test_token_hash_is_stable_and_differs_from_token(self) -> None:
        token = generate_token()

        assert hash_token(token) == hash_token(token)
        assert hash_token(token) != token

    def test_csrf_token_bound_to_session_and_secret(self) -> None:
        session = generate_token()
        csrf = csrf_token_for(session, SECRET)

        assert csrf_token_matches(session, csrf, SECRET)
        assert not csrf_token_matches(generate_token(), csrf, SECRET)
        assert not csrf_token_matches(session, csrf, "y" * 32)
        assert not csrf_token_matches(session, "", SECRET)
