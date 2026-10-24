# ADR 010: Password Reset by Email

## Status

Accepted

## Context

ADR 003 requires email-based password reset with time-limited tokens. A reset flow is a
common way to discover which addresses have accounts, to flood someone's inbox, or to take
over an account if links leak, so each of these needs a defence.

## Decision

### Requesting a link
- `POST /api/v1/auth/password-reset/request` always returns `202` with the same body. It
  only applies a per-client-address limit (default 10 per 15 minutes, `429` beyond) and
  enqueues a Dramatiq job. The account lookup happens in the worker, so neither the
  response nor its timing shows whether the account exists.
- The worker sends nothing for unknown, inactive, deleted or SSO-only accounts (the latter
  have no local password), or when SMTP is not configured (logged as a warning).
- At most 3 emails per account per hour (configurable); further requests are dropped
  silently, so the form cannot be used to flood an inbox.

### Tokens
- 256-bit random tokens. Redis stores only their SHA-256 hash, with a TTL (default 60
  minutes), mapped to the user id and a fingerprint of the user's password hash.
- Any password change alters the fingerprint, so it invalidates every outstanding link.
  Issuing a new link also deletes the previous one.
- Tokens are single-use: consumption uses `GETDEL`, so two concurrent requests cannot
  both succeed.
- The link carries the token in the URL fragment (`/reset-password#token=...`). Browsers
  never send fragments to servers, so tokens stay out of Caddy access logs and `Referer`.

### Setting the new password
- `POST /api/v1/auth/password-reset/confirm` checks the password policy *before*
  consuming the token, so a rejected password does not use up the link.
- On success: the password is set, every session of the user is revoked, sign-in delays
  for the account are cleared, and a "your password was changed" email is queued. The
  user then signs in normally (no automatic sign-in).
- `POST /api/v1/auth/change-password` sends the same notice.

### Email delivery
- Standard-library SMTP (`STARTTLS` or implicit TLS, optional login), run in the worker.
- The reset job does not retry (a retry would issue another token; the user can ask
  again). The notice job retries up to 3 times.
- An optional `mailpit` compose profile catches mail for local development.

## Consequences

- Password reset needs both SMTP settings and a running worker.
- The email address is briefly in the Redis job queue (inside the deployment), and the raw
  token exists only in the email itself.
- Email text is English only for now; translated emails can follow the UI translations.
