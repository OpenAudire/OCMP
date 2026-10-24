# ADR 009: Session, CSRF and Sign-in Rate Limiting Implementation

## Status

Accepted

## Context

ADR 003 chose server-side sessions in Redis, HTTP-only cookies and CSRF protection for
local accounts. This ADR records how they are implemented.

## Decision

### Sessions
- The cookie (`ocmp_session`) holds a random 256-bit token. Redis stores only its SHA-256
  hash, mapped to the user id, so a Redis dump does not contain usable tokens.
- 24-hour sliding expiry: each authenticated request renews the Redis TTL and the cookie.
- A per-user set of session hashes lets all of a user's sessions be revoked (password
  change revokes the others; deactivated or deleted users lose all sessions on next use).
- Sign-in always issues a new token and deletes any previous one (no session fixation).

### CSRF
- The CSRF token is `HMAC-SHA256(SECRET_KEY, "csrf:" + session token)`. It is derived, not
  stored, so `CSRFMiddleware` checks it without a Redis lookup.
- It is sent in a readable `ocmp_csrf` cookie and in the sign-in response. The frontend
  echoes it in the `X-CSRF-Token` header (axios supports this via `xsrfCookieName` /
  `xsrfHeaderName`).
- The middleware rejects any `POST`/`PUT`/`PATCH`/`DELETE` under `/api/` that carries a
  session cookie without a matching header. Sign-in is exempt (a stale cookie must not
  block signing in again); requests without a session cookie are not cookie-authenticated.
- Cookies are `SameSite=Lax`, `Secure` (configurable for local HTTP development), and the
  JSON-only API means cross-site form posts cannot reach endpoints.

### Rate limiting
- Fixed windows in Redis (default 15 minutes): all sign-in attempts per client address
  (default 20) and failed attempts per email address (default 10). A successful sign-in
  resets the account counter. Wrong current passwords on change-password count too.
- Redis keys contain hashes of the identifiers, not email addresses or IPs.
- Behind Caddy, uvicorn trusts `X-Forwarded-For` (`FORWARDED_ALLOW_IPS=*`) so limits apply to
  real client addresses. The api container publishes no ports, so only services on the
  compose network can reach it.

### Privacy
- Failed sign-ins are logged without the submitted email address. Successful sign-ins log
  the user id only.
- Unknown accounts take the same time as wrong passwords (a dummy Argon2 verification).

## Consequences

- Rotating `SECRET_KEY` invalidates all CSRF tokens; users must sign in again.
- The per-account limit lets an attacker temporarily lock out a known address. This is
  accepted for now; the window is short and configurable.
- Tests use `fakeredis`; no Redis server is needed to run them.
