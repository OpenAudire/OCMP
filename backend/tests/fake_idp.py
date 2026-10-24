"""A fake OpenID provider, served through ``httpx.MockTransport``.

Implements discovery, JWKS and the token endpoint strictly enough to check what
the client sends: redirect URI, client authentication, and PKCE.
"""

import base64
import hashlib
import json
import secrets
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

import httpx
from joserfc import jwt
from joserfc.jwk import OctKey, RSAKey

ISSUER = "https://idp.example.org/tenant-1/v2.0"
DISCOVERY_URL = f"{ISSUER}/.well-known/openid-configuration"
CLIENT_ID = "ocmp-client"
CLIENT_SECRET = "s3cret:with&odd=chars"


@dataclass
class _Grant:
    params: dict[str, str]
    claims: dict[str, Any]


@dataclass
class FakeIdP:
    issuer: str = ISSUER
    auth_methods: list[str] = field(default_factory=lambda: ["client_secret_post"])
    signing_algs: list[str] = field(default_factory=lambda: ["RS256"])
    token_status: int = 200
    omit_id_token: bool = False
    down: bool = False
    requests: list[httpx.Request] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.key = RSAKey.generate_key(2048, parameters={"kid": "key-1"})
        self.published_keys = [self.key]
        self._grants: dict[str, _Grant] = {}

    # --- what the browser would do -------------------------------------------------

    def authorize(self, authorization_url: str, **claims: Any) -> str:
        """Approve a sign-in request and return the authorization code."""
        query = {k: v[0] for k, v in parse_qs(urlsplit(authorization_url).query).items()}
        code = secrets.token_urlsafe(16)
        self._grants[code] = _Grant(params=query, claims=claims)
        return code

    # --- token building ------------------------------------------------------------

    def id_token(
        self, claims: dict[str, Any], *, key: RSAKey | OctKey | None = None, alg: str = "RS256"
    ) -> str:
        signing_key = key or self.key
        header = {"alg": alg}
        if isinstance(signing_key, RSAKey):
            header["kid"] = signing_key.kid or "key-1"
        return jwt.encode(header, claims, signing_key, algorithms=[alg])

    def default_claims(self, nonce: str, /, **overrides: Any) -> dict[str, Any]:
        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": self.issuer,
            "aud": CLIENT_ID,
            "sub": "subject-1",
            "iat": now,
            "exp": now + 300,
            "nonce": nonce,
            "email": "sso.user@example.org",
            "name": "SSO Demo User",
        }
        claims.update(overrides)
        return {k: v for k, v in claims.items() if v is not None}

    # --- HTTP ----------------------------------------------------------------------

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.down:
            raise httpx.ConnectError("provider down", request=request)
        url = str(request.url)
        if url == DISCOVERY_URL:
            return httpx.Response(200, json=self.discovery())
        if url == f"{ISSUER}/keys":
            return httpx.Response(
                200, json={"keys": [k.as_dict(private=False) for k in self.published_keys]}
            )
        if url == f"{ISSUER}/token" and request.method == "POST":
            return self._token(request)
        return httpx.Response(404)

    def discovery(self) -> dict[str, Any]:
        return {
            "issuer": self.issuer,
            "authorization_endpoint": f"{ISSUER}/authorize",
            "token_endpoint": f"{ISSUER}/token",
            "jwks_uri": f"{ISSUER}/keys",
            "token_endpoint_auth_methods_supported": self.auth_methods,
            "id_token_signing_alg_values_supported": self.signing_algs,
            "response_types_supported": ["code"],
        }

    def _token(self, request: httpx.Request) -> httpx.Response:
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        if self.token_status != 200:
            return httpx.Response(self.token_status, json={"error": "server_error"})

        if "authorization" in request.headers:
            encoded = request.headers["authorization"].removeprefix("Basic ")
            user, _, password = base64.b64decode(encoded).decode().partition(":")
            client_id, client_secret = unquote(user), unquote(password)
        else:
            client_id, client_secret = form.get("client_id", ""), form.get("client_secret", "")
        if (client_id, client_secret) != (CLIENT_ID, CLIENT_SECRET):
            return httpx.Response(401, json={"error": "invalid_client"})

        grant = self._grants.pop(form.get("code", ""), None)
        if grant is None or form.get("grant_type") != "authorization_code":
            return httpx.Response(400, json={"error": "invalid_grant"})
        if form.get("redirect_uri") != grant.params["redirect_uri"]:
            return httpx.Response(400, json={"error": "invalid_grant"})
        verifier = form.get("code_verifier", "")
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        if grant.params.get("code_challenge_method") != "S256" or (
            challenge != grant.params.get("code_challenge")
        ):
            return httpx.Response(400, json={"error": "invalid_grant", "detail": "pkce"})

        body: dict[str, Any] = {"access_token": "at", "token_type": "Bearer"}
        if not self.omit_id_token:
            claims = self.default_claims(grant.params["nonce"], **grant.claims)
            body["id_token"] = self.id_token(claims)
        return httpx.Response(
            200, content=json.dumps(body).encode(), headers={"content-type": "application/json"}
        )
