# ADR 011: Sign-in with OpenID Connect

## Status

Accepted

## Context

ADR 003 chose generic OpenID Connect via discovery, with users created on first sign-in.
Universities will mostly use Microsoft Entra ID. Sources checked on 2026-10-24:

- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html),
  section 3.1 (authorization code flow, ID token validation in 3.1.3.7)
- [RFC 9700, OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700)
  (January 2025): PKCE for confidential clients, transaction-bound state and nonce,
  exact redirect URIs
- [RFC 7636, PKCE](https://www.rfc-editor.org/rfc/rfc7636.html) (S256, appendix B vector)
- [Microsoft Entra ID token claims reference](https://learn.microsoft.com/en-us/entra/identity-platform/id-token-claims-reference):
  `email` "isn't guaranteed to be correct and is mutable over time. Never use it for
  authorization"; identify users with `sub` or `oid`
- Entra's published discovery document (`/common/v2.0/.well-known/openid-configuration`)
- [Authlib joserfc migration](https://docs.authlib.org/en/latest/upgrades/jose.html):
  `authlib.jose` and `authlib.oidc.core` are deprecated from Authlib 1.7
- [Caddy `log` directive](https://caddyserver.com/docs/caddyfile/directives/log): `filter`
  format with the `query` filter

## Decision

### Protocol
- Authorization code flow for a confidential client, with `state`, `nonce` and PKCE (S256)
  freshly generated per sign-in. They are stored in Redis (hashed key, 10-minute TTL,
  single use) and bound to the browser with an HttpOnly, `SameSite=Lax` cookie scoped to
  `/api/v1/auth/oidc`. A callback without the matching cookie is refused (login CSRF).
- Client authentication: `client_secret_post` when advertised, else `client_secret_basic`
  with form-encoded credentials (RFC 6749 section 2.3.1).
- ID token validation: signature against the provider's JWKS; algorithms limited to the
  advertised asymmetric ones (never `none` or HMAC, which blocks algorithm-confusion
  forgeries); exact `iss`; `aud` contains the client id; `azp` must be the client id when
  present or when there are several audiences; `exp` and `iat` required (60 s skew);
  `nonce` must match; `sub` required.
- Discovery is cached for an hour. Keys are cached and refetched when a token fails
  validation (key rotation), at most once a minute.
- Discovery, endpoint and key URLs must be HTTPS (`OIDC_ALLOW_INSECURE_HTTP` exists only for
  testing against a local mock provider).
- **Tenant-specific providers only.** Entra's multi-tenant `/common` endpoint publishes the
  issuer as a `{tenantid}` template, which cannot be validated exactly; it is refused with a
  message pointing to the tenant-specific discovery URL.

### Accounts
- People are identified by (issuer, `sub`), stored in `user_identities`. Email and name
  claims are contact and display details only.
- **No linking by email.** If an SSO sign-in's email matches an existing account (including
  soft-deleted ones) that is not linked to this identity, sign-in is refused
  (`account_exists`). Otherwise anyone able to set an email address at the provider could
  take over the matching local account. Linking is an administrator action (later slice).
- First sign-in creates an account without a password (`OIDC_AUTO_PROVISION`, default on).
  New accounts have no roles until assigned (Slice 0.8). Email falls back to
  `preferred_username` when it looks like an address (Entra omits `email` by default).
- Disabled or deleted accounts cannot sign in. Successful sign-in creates a normal OCMP
  session (ADR 009).
- The account logic (`app/services/sso.py`) is protocol-independent so SAML (phase 2) can
  reuse it.

### Browser flow and errors
- `GET /api/v1/auth/oidc` (is SSO on, provider name), `GET /api/v1/auth/oidc/login?next=`
  (redirect to provider), `GET /api/v1/auth/oidc/callback` (redirect to `next`).
- `next` must be a path on this site (no open redirects).
- Failures redirect to `/login?sso_error=<code>`: `sso_unavailable`, `sso_failed`,
  `sso_cancelled`, `sso_expired`, `account_disabled`, `account_exists`, `no_email`,
  `not_provisioned`, `too_many_attempts`. Details go to the log only.
- Caddy redacts `code` and `state` from access logs.

### Library
- HTTP with `httpx`; ID token verification with `joserfc` (replacing the unused
  `python-jose`), avoiding Authlib's deprecated `authlib.jose` path.

## Consequences

- Entra registration: platform "Web", redirect URI
  `https://<domain>/api/v1/auth/oidc/callback`, a client secret, and the tenant-specific
  discovery URL `https://login.microsoftonline.com/<tenant-id>/v2.0/.well-known/openid-configuration`.
- Configuration is per instance (environment), not per institution, until multi-institution
  support is needed.
- Not yet implemented: provider logout (RP-initiated logout), role mapping from claims
  (needs Slice 0.8), admin linking of existing accounts, multi-tenant Entra.
