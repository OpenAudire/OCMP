"""OpenID Connect relying party (authorization code flow with PKCE).

Implements OpenID Connect Core 1.0 and Discovery 1.0 for a confidential
client, following RFC 9700 (OAuth 2.0 Security BCP): exact redirect URI,
transaction-specific ``state``, ``nonce`` and PKCE (S256) values, and the
ID token validation rules of OIDC Core section 3.1.3.7.

Only tenant- or realm-specific providers are supported: the issuer in the
discovery document must be a concrete URL (Microsoft's multi-tenant
``/common`` endpoint publishes a ``{tenantid}`` template, which cannot be
validated exactly).
"""

import base64
import hashlib
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpx
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet
from joserfc.jwt import JWTClaimsRegistry

from app.core.config import Settings

# Public-key algorithms only: never "none", and never HMAC (which would make the
# client secret a signing key).
ASYMMETRIC_ALGORITHMS = frozenset(
    {"RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512", "EdDSA"}
)


class OIDCError(Exception):
    """Sign-in with the provider failed. ``code`` is safe to show to the user."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class ProviderMetadata:
    """The parts of the discovery document the client uses."""

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    token_auth_method: str  # "client_secret_post" or "client_secret_basic"
    signing_algorithms: frozenset[str]


def pkce_challenge(verifier: str) -> str:
    """S256 code challenge for a PKCE verifier (RFC 7636 section 4.2)."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class OIDCClient:
    """Client for one configured OpenID provider. Caches discovery and keys."""

    def __init__(
        self,
        settings: Settings,
        http: httpx.AsyncClient,
        *,
        metadata_ttl_seconds: float = 3600.0,
        jwks_min_refresh_seconds: float = 60.0,
    ) -> None:
        if not settings.oidc_configured:
            raise ValueError("OIDC is not configured.")
        self.settings = settings
        self.http = http
        self._metadata_ttl = metadata_ttl_seconds
        self._jwks_min_refresh = jwks_min_refresh_seconds
        self._metadata: ProviderMetadata | None = None
        self._metadata_at = 0.0
        self._keys: KeySet | None = None
        self._keys_at = 0.0

    @property
    def client_id(self) -> str:
        assert self.settings.oidc_client_id is not None
        return self.settings.oidc_client_id

    def _check_url(self, url: object, what: str) -> str:
        if not isinstance(url, str) or not url:
            raise OIDCError("sso_unavailable", f"Provider metadata has no {what}.")
        scheme = urlsplit(url).scheme
        if scheme != "https" and not (scheme == "http" and self.settings.oidc_allow_insecure_http):
            raise OIDCError("sso_unavailable", f"Provider {what} must use HTTPS.")
        return url

    async def _get_json(self, url: str) -> dict[str, Any]:
        try:
            response = await self.http.get(url)
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise OIDCError("sso_unavailable", "Could not reach the sign-in provider.") from exc
        if not isinstance(data, dict):
            raise OIDCError("sso_unavailable", "Unexpected response from the sign-in provider.")
        return data

    async def metadata(self) -> ProviderMetadata:
        """Discovery document (cached)."""
        if self._metadata and time.monotonic() - self._metadata_at < self._metadata_ttl:
            return self._metadata

        url = self._check_url(self.settings.oidc_discovery_url, "discovery URL")
        doc = await self._get_json(url)
        issuer = self._check_url(doc.get("issuer"), "issuer")
        if "{" in issuer:
            raise OIDCError(
                "sso_unavailable",
                "The provider's issuer is a template (multi-tenant endpoint). "
                "Use the tenant-specific discovery URL.",
            )

        methods = doc.get("token_endpoint_auth_methods_supported") or ["client_secret_basic"]
        if "client_secret_post" in methods:
            auth_method = "client_secret_post"
        elif "client_secret_basic" in methods:
            auth_method = "client_secret_basic"
        else:
            raise OIDCError("sso_unavailable", "Provider supports no client secret method.")

        advertised = set(doc.get("id_token_signing_alg_values_supported") or ["RS256"])
        algorithms = frozenset(advertised & ASYMMETRIC_ALGORITHMS)
        if not algorithms:
            raise OIDCError(
                "sso_unavailable", "Provider signs ID tokens with no allowed algorithm."
            )

        self._metadata = ProviderMetadata(
            issuer=issuer,
            authorization_endpoint=self._check_url(
                doc.get("authorization_endpoint"), "authorization endpoint"
            ),
            token_endpoint=self._check_url(doc.get("token_endpoint"), "token endpoint"),
            jwks_uri=self._check_url(doc.get("jwks_uri"), "JWKS URI"),
            token_auth_method=auth_method,
            signing_algorithms=algorithms,
        )
        self._metadata_at = time.monotonic()
        return self._metadata

    async def _key_set(self, *, refresh: bool = False) -> KeySet:
        """Provider signing keys (cached; refreshed on demand, at most once a minute)."""
        stale = time.monotonic() - self._keys_at >= self._jwks_min_refresh
        if self._keys is None or (refresh and stale):
            metadata = await self.metadata()
            data = await self._get_json(metadata.jwks_uri)
            try:
                self._keys = KeySet.import_key_set(data)  # type: ignore[arg-type]
            except (JoseError, ValueError, KeyError, TypeError) as exc:
                raise OIDCError("sso_unavailable", "Provider published invalid keys.") from exc
            self._keys_at = time.monotonic()
        return self._keys

    async def authorization_url(self, *, state: str, nonce: str, code_verifier: str) -> str:
        """Where to send the browser to sign in."""
        metadata = await self.metadata()
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.settings.oidc_redirect_uri,
            "scope": self.settings.oidc_scopes,
            "state": state,
            "nonce": nonce,
            "code_challenge": pkce_challenge(code_verifier),
            "code_challenge_method": "S256",
        }
        separator = "&" if "?" in metadata.authorization_endpoint else "?"
        return f"{metadata.authorization_endpoint}{separator}{urlencode(params)}"

    async def exchange_code(self, *, code: str, code_verifier: str) -> str:
        """Redeem the authorization code; returns the raw ID token."""
        metadata = await self.metadata()
        secret = self.settings.oidc_client_secret
        assert secret is not None
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.settings.oidc_redirect_uri,
            "code_verifier": code_verifier,
        }
        extra: dict[str, Any] = {}
        if metadata.token_auth_method == "client_secret_post":  # noqa: S105 (method name)
            form |= {"client_id": self.client_id, "client_secret": secret}
        else:
            # RFC 6749 section 2.3.1: form-encode the credentials before Basic auth.
            extra["auth"] = httpx.BasicAuth(_form_encode(self.client_id), _form_encode(secret))

        try:
            response = await self.http.post(
                metadata.token_endpoint,
                data=form,
                **extra,
                headers={"Accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise OIDCError("sso_unavailable", "Could not reach the sign-in provider.") from exc
        if response.status_code != 200:
            raise OIDCError("sso_failed", f"Token request rejected ({response.status_code}).")
        try:
            id_token = response.json().get("id_token")
        except ValueError as exc:
            raise OIDCError("sso_failed", "Token response was not JSON.") from exc
        if not isinstance(id_token, str) or not id_token:
            raise OIDCError("sso_failed", "Token response had no ID token.")
        return id_token

    async def validate_id_token(self, id_token: str, *, nonce: str) -> dict[str, Any]:
        """Verify the ID token's signature and claims (OIDC Core 3.1.3.7)."""
        metadata = await self.metadata()
        algorithms = sorted(metadata.signing_algorithms)
        try:
            try:
                token = jwt.decode(id_token, await self._key_set(), algorithms=algorithms)
            except (JoseError, ValueError):
                # Possibly signed with a newly rotated key: refresh the keys once.
                token = jwt.decode(
                    id_token, await self._key_set(refresh=True), algorithms=algorithms
                )
        except (JoseError, ValueError) as exc:
            raise OIDCError("sso_failed", "ID token signature is invalid.") from exc

        claims = token.claims
        registry = JWTClaimsRegistry(
            leeway=self.settings.oidc_clock_skew_seconds,
            iss={"essential": True, "value": metadata.issuer},
            aud={"essential": True, "value": self.client_id},
            sub={"essential": True},
            exp={"essential": True},
            iat={"essential": True},
            nonce={"essential": True, "value": nonce},
        )
        try:
            registry.validate(claims)
        except JoseError as exc:
            raise OIDCError("sso_failed", f"ID token rejected: {exc}") from exc

        # With several audiences, the authorized party must be this client.
        audiences = claims["aud"] if isinstance(claims["aud"], list) else [claims["aud"]]
        if (len(audiences) > 1 or "azp" in claims) and claims.get("azp") != self.client_id:
            raise OIDCError("sso_failed", "ID token was issued to a different client.")
        if not isinstance(claims["sub"], str) or not claims["sub"]:
            raise OIDCError("sso_failed", "ID token has no subject.")
        return claims


def _form_encode(value: str) -> str:
    return urlencode({"": value})[1:]
