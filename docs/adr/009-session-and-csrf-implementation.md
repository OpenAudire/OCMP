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

### Sign-in throttling
Two mechanisms, deliberately different:

- **Per client address: hard limit.** At most 20 sign-in attempts per address per
  15-minute window (configurable); further attempts get `429` with `Retry-After`. This
  also caps how many delayed requests one client can hold open.
- **Per account: progressive delay, never a lockout.** Failed attempts against an email
  address are counted in a 15-minute window. After 3 free failures, each attempt on that
  account is held back before the password is checked: 1 s, then doubling per further
  failure, capped at 20 s (all configurable). The attempt is never refused, so the owner can
  always sign in with the right password, at worst after the maximum delay. A successful
  sign-in clears the count. Wrong current passwords on change-password are counted and
  delayed the same way.
- Redis keys contain hashes of the identifiers, not email addresses or IPs.

*Revised 2026-10-24:* the first version also locked an account (`429`) after 10 failed
attempts. That let anyone who knew an address lock its owner out, so it was replaced by
the progressive delay.

### Client address and trusted proxies
- The app works out the client address itself; uvicorn runs with `--no-proxy-headers`.
- `X-Forwarded-For` is used only when the connecting peer is in `TRUSTED_PROXIES`
  (IP addresses, CIDR networks or hostnames; default `caddy`, the compose service).
  Otherwise the peer address is used, so clients cannot spoof their address.
- Hostnames are resolved through DNS and cached for 30 s. An unknown peer triggers a fresh
  lookup at most every 5 s, so a restarted Caddy container with a new IP is picked up.
- The header is read from the right: the first address that is not itself a trusted
  proxy is the client. Malformed entries stop the walk and the peer address is used.

### Privacy
- Failed sign-ins are logged without the submitted email address. Successful sign-ins log
  the user id only.
- Unknown accounts take the same time as wrong passwords (a dummy Argon2 verification).

## Consequences

- Rotating `SECRET_KEY` invalidates all CSRF tokens; users must sign in again.
- Nobody can lock another user out. The trade-off is that the delay throttles guesses
  against one account but cannot stop guessing spread over many addresses (each subject
  to its own 20-per-window limit, and attempts on one account still run in parallel).
  Stronger defences (MFA, breached-password checks) are future work.
- Sites with another reverse proxy in front of Caddy (e.g. a university load balancer)
  must add it to `TRUSTED_PROXIES`, or all clients will share that proxy's address.
- Tests use `fakeredis`; no Redis server is needed to run them.
