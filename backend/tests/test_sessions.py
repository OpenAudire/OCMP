"""Tests for the Redis session store and rate limiter."""

import uuid

import pytest
from fakeredis import FakeAsyncRedis

from app.services import rate_limit, sessions

TTL = 3600


class TestSessions:
    async def test_create_and_resolve(self, redis_client: FakeAsyncRedis) -> None:
        user_id = uuid.uuid4()
        token = await sessions.create_session(redis_client, user_id, TTL)

        session = await sessions.get_session(redis_client, token, TTL)

        assert session is not None
        assert session.user_id == user_id

    async def test_unknown_token_resolves_to_nothing(self, redis_client: FakeAsyncRedis) -> None:
        assert await sessions.get_session(redis_client, "no-such-token", TTL) is None

    async def test_raw_token_is_not_stored(self, redis_client: FakeAsyncRedis) -> None:
        token = await sessions.create_session(redis_client, uuid.uuid4(), TTL)

        keys = await redis_client.keys("*")
        values = [await redis_client.get(k) for k in keys if await redis_client.type(k) == "string"]
        assert not any(token in k for k in keys)
        assert not any(token in v for v in values if v)

    async def test_access_extends_expiry(self, redis_client: FakeAsyncRedis) -> None:
        token = await sessions.create_session(redis_client, uuid.uuid4(), 60)
        (key,) = await redis_client.keys("ocmp:session:*")

        await sessions.get_session(redis_client, token, TTL)

        assert await redis_client.ttl(key) > 60

    async def test_delete_session(self, redis_client: FakeAsyncRedis) -> None:
        user_id = uuid.uuid4()
        token = await sessions.create_session(redis_client, user_id, TTL)

        await sessions.delete_session(redis_client, token)

        assert await sessions.get_session(redis_client, token, TTL) is None
        assert await redis_client.smembers(f"ocmp:user-sessions:{user_id}") == set()

    async def test_revoke_all_but_current(self, redis_client: FakeAsyncRedis) -> None:
        user_id = uuid.uuid4()
        other_user_token = await sessions.create_session(redis_client, uuid.uuid4(), TTL)
        current = await sessions.create_session(redis_client, user_id, TTL)
        elsewhere = await sessions.create_session(redis_client, user_id, TTL)

        revoked = await sessions.revoke_user_sessions(redis_client, user_id, keep_token=current)

        assert revoked == 1
        assert await sessions.get_session(redis_client, current, TTL) is not None
        assert await sessions.get_session(redis_client, elsewhere, TTL) is None
        assert await sessions.get_session(redis_client, other_user_token, TTL) is not None

    async def test_revoke_with_no_sessions(self, redis_client: FakeAsyncRedis) -> None:
        assert await sessions.revoke_user_sessions(redis_client, uuid.uuid4()) == 0


class TestRateLimit:
    async def test_blocks_at_limit_until_reset(self, redis_client: FakeAsyncRedis) -> None:
        for _ in range(3):
            assert (await rate_limit.check(redis_client, "s", "id", 3)).allowed
            await rate_limit.hit(redis_client, "s", "id", 60)

        status = await rate_limit.check(redis_client, "s", "id", 3)
        assert not status.allowed
        assert 0 < status.retry_after_seconds <= 60

        await rate_limit.reset(redis_client, "s", "id")
        assert (await rate_limit.check(redis_client, "s", "id", 3)).allowed

    async def test_identifiers_are_case_insensitive_and_hashed(
        self, redis_client: FakeAsyncRedis
    ) -> None:
        await rate_limit.hit(redis_client, "s", "Lecturer@Example.test", 60)

        assert not (await rate_limit.check(redis_client, "s", "lecturer@example.test", 1)).allowed
        assert not any("lecturer" in k.lower() for k in await redis_client.keys("*"))


class TestProgressiveDelay:
    @pytest.mark.parametrize(
        ("failures", "expected"),
        [(0, 0.0), (2, 0.0), (3, 1.0), (4, 2.0), (5, 4.0), (7, 16.0), (8, 20.0), (10**6, 20.0)],
    )
    def test_schedule(self, failures: int, expected: float) -> None:
        delay = rate_limit.progressive_delay_seconds(
            failures, free_failures=3, base_seconds=1.0, max_seconds=20.0
        )

        assert delay == expected

    async def test_count(self, redis_client: FakeAsyncRedis) -> None:
        assert await rate_limit.count(redis_client, "s", "id") == 0
        await rate_limit.hit(redis_client, "s", "id", 60)
        await rate_limit.hit(redis_client, "s", "id", 60)

        assert await rate_limit.count(redis_client, "s", "id") == 2
