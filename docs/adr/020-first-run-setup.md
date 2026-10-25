# ADR 020: First-Run Setup

## Status

Accepted

## Context

The brief (section 7) says a fresh install starts with `docker compose up -d` and a
first-run setup wizard creates the first admin and the institution. The setup endpoint
must work before anyone can sign in, so whoever reaches a new server first could otherwise
claim the administrator account: a real risk for a server on a university network.

## Decision

### Setup token
- Setup requires a token only the server operator can see. It is derived from `SECRET_KEY`
  (`HMAC-SHA256(SECRET_KEY, "ocmp-setup")`, first 80 bits, Base32, shown as
  `XXXX-XXXX-XXXX-XXXX`). Nothing is stored.
- While setup is pending the API prints it in its log at startup, and
  `python -m app.cli setup-token` shows it. Once setup is done the command says so and the
  API stops printing it.
- Comparison is constant-time and ignores case, spaces and dashes. Attempts are limited
  per client address (10 per 15 minutes).

### Once only, all or nothing
- Setup is open only while no institution exists (`GET /api/v1/setup/status`).
- `POST /api/v1/setup` takes a Postgres advisory transaction lock and re-checks, so two
  simultaneous attempts cannot both succeed; later attempts get `409`.
- It creates, inside one savepoint: the institution (name, short code, country, optional
  health profile), the admin account (normal password policy) and the `platform_admin`
  role. A rejected account leaves nothing behind. Everything is audited as the
  `setup.complete` operation.
- The admin is signed in immediately (new session and CSRF cookies). Like sign-in, the
  endpoint is exempt from the CSRF check, so a stale cookie from an earlier install cannot
  block it.

### Wizard
- `/setup`: three steps (institution with the setup token, administrator, confirm), each
  validated before moving on. A wrong token returns to the first step; `409` explains that
  setup is complete and links to sign-in.
- The sign-in page sends visitors to `/setup` while setup is pending; `/setup` sends them to
  sign-in afterwards.

## Consequences

- The install guide (Slice 0.19) must include reading the token from
  `docker compose logs api` or the `setup-token` command.
- Anyone who has `SECRET_KEY` can compute the token, which is acceptable: they already
  control the server. Rotating `SECRET_KEY` changes the token.
- `python -m app.cli create-admin` remains the recovery path; it does not create an
  institution, so the wizard stays available until one exists.
