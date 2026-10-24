"""Tests for the OpenID Connect client against a fake provider."""

import time
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from joserfc.jwk import OctKey, RSAKey

from app.core.config import Settings
from app.services.oidc import OIDCClient, OIDCError, pkce_challenge
from tests.fake_idp import CLIENT_ID, CLIENT_SECRET, DISCOVERY_URL, ISSUER, FakeIdP

NONCE = "nonce-123"


def oidc_settings(test_settings: Settings, **overrides: Any) -> Settings:
    values = {
        "oidc_enabled": True,
        "oidc_discovery_url": DISCOVERY_URL,
        "oidc_client_id": CLIENT_ID,
        "oidc_client_secret": CLIENT_SECRET,
        "public_url": "https://ocmp.example.org",
        **overrides,
    }
    return test_settings.model_copy(update=values)


@pytest.fixture
def idp() -> FakeIdP:
    return FakeIdP()


@pytest.fixture
def client(idp: FakeIdP, test_settings: Settings) -> OIDCClient:
    return OIDCClient(oidc_settings(test_settings), httpx.AsyncClient(transport=idp.transport))


def make_client(idp: FakeIdP, settings: Settings, **kwargs: Any) -> OIDCClient:
    return OIDCClient(settings, httpx.AsyncClient(transport=idp.transport), **kwargs)


def test_pkce_matches_rfc_7636_example() -> None:
    # RFC 7636 appendix B.
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"

    assert pkce_challenge(verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_requires_configuration(test_settings: Settings) -> None:
    with pytest.raises(ValueError, match="not configured"):
        OIDCClient(test_settings, httpx.AsyncClient())


class TestDiscovery:
    async def test_reads_metadata_and_caches_it(self, client: OIDCClient, idp: FakeIdP) -> None:
        first = await client.metadata()
        await client.metadata()

        assert first.issuer == ISSUER
        assert first.token_auth_method == "client_secret_post"
        assert first.signing_algorithms == {"RS256"}
        assert len(idp.requests) == 1

    async def test_templated_multi_tenant_issuer_is_refused(
        self, idp: FakeIdP, test_settings: Settings
    ) -> None:
        idp.issuer = "https://login.microsoftonline.com/{tenantid}/v2.0"
        client = make_client(idp, oidc_settings(test_settings))

        with pytest.raises(OIDCError, match="tenant-specific") as exc:
            await client.metadata()
        assert exc.value.code == "sso_unavailable"

    async def test_http_urls_are_refused(self, idp: FakeIdP, test_settings: Settings) -> None:
        settings = oidc_settings(
            test_settings, oidc_discovery_url="http://idp.example.org/.well-known/x"
        )

        with pytest.raises(OIDCError, match="HTTPS"):
            await make_client(idp, settings).metadata()

    async def test_only_symmetric_algorithms_is_refused(
        self, idp: FakeIdP, test_settings: Settings
    ) -> None:
        idp.signing_algs = ["HS256", "none"]

        with pytest.raises(OIDCError, match="no allowed algorithm"):
            await make_client(idp, oidc_settings(test_settings)).metadata()

    async def test_provider_down(self, idp: FakeIdP, client: OIDCClient) -> None:
        idp.down = True

        with pytest.raises(OIDCError) as exc:
            await client.metadata()
        assert exc.value.code == "sso_unavailable"


class TestAuthorizationUrl:
    async def test_contains_required_parameters(self, client: OIDCClient) -> None:
        url = await client.authorization_url(state="st", nonce="no", code_verifier="v" * 43)

        assert url.startswith(f"{ISSUER}/authorize?")
        params = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
        assert params == {
            "response_type": "code",
            "client_id": CLIENT_ID,
            "redirect_uri": "https://ocmp.example.org/api/v1/auth/oidc/callback",
            "scope": "openid profile email",
            "state": "st",
            "nonce": "no",
            "code_challenge": pkce_challenge("v" * 43),
            "code_challenge_method": "S256",
        }


class TestCodeExchange:
    async def get_code(self, client: OIDCClient, idp: FakeIdP, verifier: str) -> str:
        url = await client.authorization_url(state="s", nonce=NONCE, code_verifier=verifier)
        return idp.authorize(url)

    @pytest.mark.parametrize("method", ["client_secret_post", "client_secret_basic"])
    async def test_exchanges_code_with_client_secret(
        self, idp: FakeIdP, test_settings: Settings, method: str
    ) -> None:
        idp.auth_methods = [method]
        client = make_client(idp, oidc_settings(test_settings))
        code = await self.get_code(client, idp, "verifier-" + "x" * 40)

        id_token = await client.exchange_code(code=code, code_verifier="verifier-" + "x" * 40)

        claims = await client.validate_id_token(id_token, nonce=NONCE)
        assert claims["sub"] == "subject-1"

    async def test_wrong_verifier_is_rejected_by_provider(
        self, client: OIDCClient, idp: FakeIdP
    ) -> None:
        code = await self.get_code(client, idp, "a" * 43)

        with pytest.raises(OIDCError) as exc:
            await client.exchange_code(code=code, code_verifier="b" * 43)
        assert exc.value.code == "sso_failed"

    async def test_provider_error(self, client: OIDCClient, idp: FakeIdP) -> None:
        code = await self.get_code(client, idp, "a" * 43)
        idp.token_status = 500

        with pytest.raises(OIDCError, match="rejected"):
            await client.exchange_code(code=code, code_verifier="a" * 43)

    async def test_missing_id_token(self, client: OIDCClient, idp: FakeIdP) -> None:
        code = await self.get_code(client, idp, "a" * 43)
        idp.omit_id_token = True

        with pytest.raises(OIDCError, match="no ID token"):
            await client.exchange_code(code=code, code_verifier="a" * 43)


class TestIdTokenValidation:
    async def test_valid_token(self, client: OIDCClient, idp: FakeIdP) -> None:
        claims = await client.validate_id_token(
            idp.id_token(idp.default_claims(NONCE)), nonce=NONCE
        )

        assert claims["email"] == "sso.user@example.org"

    @pytest.mark.parametrize(
        "overrides",
        [
            {"iss": "https://evil.example.org"},
            {"aud": "another-client"},
            {"exp": int(time.time()) - 3600},
            {"iat": None},
            {"nonce": "different"},
            {"nonce": None},
            {"sub": None},
            {"aud": [CLIENT_ID, "another-client"]},  # several audiences, no azp
            {"azp": "another-client"},
        ],
        ids=[
            "wrong-issuer",
            "wrong-audience",
            "expired",
            "no-iat",
            "wrong-nonce",
            "no-nonce",
            "no-subject",
            "multi-aud-no-azp",
            "wrong-azp",
        ],
    )
    async def test_invalid_claims_are_rejected(
        self, client: OIDCClient, idp: FakeIdP, overrides: dict[str, Any]
    ) -> None:
        token = idp.id_token(idp.default_claims(NONCE, **overrides))

        with pytest.raises(OIDCError) as exc:
            await client.validate_id_token(token, nonce=NONCE)
        assert exc.value.code == "sso_failed"

    async def test_multiple_audiences_with_matching_azp(
        self, client: OIDCClient, idp: FakeIdP
    ) -> None:
        token = idp.id_token(idp.default_claims(NONCE, aud=[CLIENT_ID, "other"], azp=CLIENT_ID))

        assert (await client.validate_id_token(token, nonce=NONCE))["sub"] == "subject-1"

    async def test_clock_skew_is_tolerated(self, client: OIDCClient, idp: FakeIdP) -> None:
        token = idp.id_token(idp.default_claims(NONCE, exp=int(time.time()) - 30))

        await client.validate_id_token(token, nonce=NONCE)

    async def test_token_signed_by_unknown_key(self, client: OIDCClient, idp: FakeIdP) -> None:
        stranger = RSAKey.generate_key(2048, parameters={"kid": "key-1"})
        token = idp.id_token(idp.default_claims(NONCE), key=stranger)

        with pytest.raises(OIDCError, match="signature"):
            await client.validate_id_token(token, nonce=NONCE)

    async def test_hmac_token_signed_with_client_secret_is_rejected(
        self, client: OIDCClient, idp: FakeIdP
    ) -> None:
        # Classic algorithm-confusion attack: HS256 keyed with the client secret.
        forged = idp.id_token(
            idp.default_claims(NONCE), key=OctKey.import_key(CLIENT_SECRET), alg="HS256"
        )

        with pytest.raises(OIDCError):
            await client.validate_id_token(forged, nonce=NONCE)

    async def test_unsigned_token_is_rejected(self, client: OIDCClient, idp: FakeIdP) -> None:
        import base64
        import json

        def b64(data: dict[str, Any]) -> str:
            return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

        unsigned = f"{b64({'alg': 'none'})}.{b64(idp.default_claims(NONCE))}."

        with pytest.raises(OIDCError):
            await client.validate_id_token(unsigned, nonce=NONCE)

    async def test_key_rotation_is_picked_up(self, idp: FakeIdP, test_settings: Settings) -> None:
        client = make_client(idp, oidc_settings(test_settings), jwks_min_refresh_seconds=0)
        await client.validate_id_token(idp.id_token(idp.default_claims(NONCE)), nonce=NONCE)

        # Provider rotates to a new signing key.
        new_key = RSAKey.generate_key(2048, parameters={"kid": "key-2"})
        idp.published_keys = [new_key]
        token = idp.id_token(idp.default_claims(NONCE), key=new_key)

        assert (await client.validate_id_token(token, nonce=NONCE))["sub"] == "subject-1"

    async def test_keys_are_not_refetched_on_every_bad_token(
        self, client: OIDCClient, idp: FakeIdP
    ) -> None:
        await client.validate_id_token(idp.id_token(idp.default_claims(NONCE)), nonce=NONCE)
        stranger = RSAKey.generate_key(2048, parameters={"kid": "nope"})
        jwks_fetches_before = sum(1 for r in idp.requests if r.url.path.endswith("/keys"))

        for _ in range(3):
            with pytest.raises(OIDCError):
                await client.validate_id_token(
                    idp.id_token(idp.default_claims(NONCE), key=stranger), nonce=NONCE
                )

        jwks_fetches = sum(1 for r in idp.requests if r.url.path.endswith("/keys"))
        assert jwks_fetches == jwks_fetches_before
