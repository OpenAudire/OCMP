# OCMP Development Progress

This file tracks progress through the development phases.

## Current Phase: Phase 1 - Core Mapping (Phase 0 approved 2026-10-25)

### Slice 0.1: Project Scaffold
**Status**: Complete

**Deliverables**:
- [x] Monorepo structure created
- [x] Backend `pyproject.toml` with ruff, mypy, pytest configuration
- [x] Frontend `package.json` with Vite, TypeScript, Mantine, ESLint
- [x] `.gitignore` for Python, Node.js, IDE files
- [x] `.pre-commit-config.yaml` with hooks for linting
- [x] GitHub Actions CI workflow (`ci.yml`)
- [x] Backend app structure (`app/api`, `app/core`, `app/models`, etc.)
- [x] Frontend app structure with i18n setup
- [x] ADRs 001-007 created
- [x] `CLAUDE.md` conventions file created
- [x] Basic health endpoint tests
- [x] Docker Compose configuration
- [x] Framework pack schema and demo pack

**Verification**:
- Backend linting: `ruff check .` passes
- Backend type check: `mypy app` passes
- Backend tests: `pytest` passes (2 tests, 100% coverage)
- Frontend linting: `npm run lint` passes
- Frontend type check: `npm run typecheck` passes
- Frontend tests: `npm run test` passes (1 test)

**Commit**: `feat: initial project scaffold with linting and CI` (0dcbdea)

---

### Slice 0.2: Docker Compose Base Stack
**Status**: Complete

**Deliverables**:
- [x] Backend Dockerfile installs dependencies in a cached layer (previous editable install failed before app code was copied)
- [x] `.dockerignore` for backend and frontend (keeps `.venv` and Windows `node_modules` out of the build context)
- [x] Dramatiq worker entry point (`app/worker.py`) with a `ping` actor
- [x] One-shot `migrate` service runs `alembic upgrade head`; `api` and `worker` wait for it to succeed
- [x] `api`, `worker` and `migrate` share one image (`ocmp-backend:local`); compose project named `ocmp`
- [x] Frontend production build fixed (`vite.config.ts` uses `vitest/config` and `import.meta.url`; `@types/node` added)
- [x] Web container healthcheck uses `127.0.0.1` (busybox `localhost` resolves to IPv6)

**Verification** (Docker Desktop 29.9, Compose v5.6):
- `docker compose up -d --wait` from `deploy/` after copying `.env.example` to `.env`: all services healthy, `migrate` exits 0
- `https://localhost/health` -> healthy; `https://localhost/ready` -> database up, redis up
- `https://localhost/` serves the React app; `http://` redirects to `https://`
- Job enqueued from the api container is consumed by the worker
- Backend: ruff, ruff format, mypy, pytest (13 passed) all pass
- Frontend: `npm run build`, lint, typecheck, test all pass

**Commit**: `feat: make Docker Compose stack build and start`

---

### Slice 0.3: Backend Core + Health Endpoints
**Status**: Complete

**Deliverables**:
- [x] Configuration system using pydantic-settings (`app/core/config.py`)
- [x] Structured logging with structlog (`app/core/logging.py`)
- [x] Database connection management (`app/core/database.py`)
- [x] Redis connection management (`app/core/redis.py`)
- [x] Health check router with `/health` and `/ready` endpoints (`app/api/health.py`)
- [x] FastAPI app with lifespan management (`app/main.py`)
- [x] CORS middleware configured
- [x] Virtual environment setup at `backend/.venv`
- [x] All dependencies in `pyproject.toml`
- [x] `.gitattributes` for LF line endings

**Verification**:
- Ruff: `ruff check .` passes
- Mypy: `mypy app` passes (no issues in 14 files)
- Pytest: 13 tests pass, 62% coverage

**Commit**: `feat: add backend core with config, logging, and health endpoints` (9ef145d)

---

### Slice 0.4: Database Models (Core)
**Status**: Complete

**Deliverables**:
- [x] `app/models/base.py`: `Base` with constraint naming convention; mixins for UUID PK, timestamps, `created_by_id`, soft delete; `CoreModel` abstract base
- [x] Models: `Institution` (country, settings JSONB), `Faculty`, `Department`, `User` (identity only; auth fields come in Slice 0.5)
- [x] Alembic wired to model metadata (`compare_type`, `compare_server_default`); migration template uses modern typing; post-write hook runs `ruff check --fix` and `ruff format`
- [x] Migrations: `0001` enables `vector`; `0002` adds core organisation and user tables
- [x] Test harness against real PostgreSQL (`TEST_DATABASE_URL`), migrations once per session, per-test rollback
- [x] factory_boy factories (`tests/factories.py`) with fictional data
- [x] Migration drift test (`alembic check`) and downgrade/upgrade round trip
- [x] CI sets `TEST_DATABASE_URL` so database tests never skip there
- [x] ADR 008: core data model conventions

**Verification**:
- Ruff, ruff format, mypy (18 files) pass
- Pytest: 29 passed against `pgvector/pgvector:pg16` (15 database tests skip when `TEST_DATABASE_URL` is unset)
- `docker compose up` runs `0001` and `0002` in the `migrate` service; tables and `vector` extension present

**Commit**: `feat: add core database models and migrations`

---

### Slice 0.5: Auth: Local Accounts
**Status**: Complete

**Deliverables**:
- [x] `User.password_hash` (nullable for SSO-only users), migration `0003`
- [x] Argon2id hashing with automatic rehash on sign-in, password policy (12-256 characters, not the email address), constant-time handling of unknown accounts (`app/core/security.py`)
- [x] Redis session store with hashed tokens, sliding 24h expiry, revoke-all per user (`app/services/sessions.py`)
- [x] CSRF middleware with session-derived HMAC tokens (`app/core/csrf.py`)
- [x] Sign-in rate limiting per client address and per account (`app/services/rate_limit.py`)
- [x] User service: `create_local_user`, `authenticate`, `change_password` (`app/services/users.py`)
- [x] Endpoints: `POST /api/v1/auth/login`, `POST /api/v1/auth/logout`, `GET /api/v1/auth/me`, `POST /api/v1/auth/change-password`
- [x] API dependencies `CurrentUser` / `CurrentAuth` for protected routes (`app/api/deps.py`)
- [x] uvicorn trusts Caddy's forwarded headers in Docker; session and rate limit settings in `.env.example`
- [x] ADR 009: session, CSRF and rate limiting implementation
- [x] Test fixes: env defaults in `conftest.py` replace patching `app.core.config.get_settings` (which leaked a mock into `Depends`); coverage traces greenlets so SQLAlchemy async code is measured

**Not in this slice**: creating users through the API needs roles (Slice 0.8); the first admin is created by the setup wizard (Slice 0.17).

**Verification**:
- Ruff, ruff format, mypy (27 files) pass
- Pytest: 91 passed, 86% total coverage; auth router, deps, security, sessions, rate limit and user service at 98-100%
- End to end through Caddy: sign-in, `/me`, logout rejected without CSRF header (403) and accepted with it (204), `/me` afterwards 401, 11th failed sign-in returns 429; no email addresses in API logs

**Commit**: `feat: add local account authentication with sessions and CSRF` (7f97770)

**Follow-up** (`fix: throttle sign-in without account lockout and trust only Caddy`):
- [x] Per-account lockout replaced by progressive delays (3 free failures, then 1 s doubling to a 20 s cap; never refused); per-IP hard limit kept
- [x] Client address resolved in the app from `X-Forwarded-For` only when the peer is in `TRUSTED_PROXIES` (IPs, CIDRs or hostnames, default `caddy`); uvicorn runs with `--no-proxy-headers`
- [x] Comma-separated list settings from the environment fixed (`CORS_ORIGINS` previously crashed settings loading)
- [x] ADR 009 revised
- Verification: 127 tests pass, 88% coverage (auth, deps, proxy, rate limit 100%). End to end through Caddy: rotating spoofed `X-Forwarded-For` still hits the per-IP 429, both through Caddy and directly from another container; a second client through Caddy is limited separately; after 6 failures the owner signs in with the right password after an 8 s delay

---

### Slice 0.6: Auth: Password Reset
**Status**: Complete

**Deliverables**:
- [x] `POST /api/v1/auth/password-reset/request`: always `202`, per-IP limit, account lookup in a background job (no enumeration by content or timing)
- [x] `POST /api/v1/auth/password-reset/confirm`: policy checked before the token is consumed; revokes all sessions; clears sign-in delays
- [x] Tokens in Redis as hashes with TTL, single-use (`GETDEL`), bound to a password-hash fingerprint, one live token per user; token in the URL fragment
- [x] Silent cap of 3 reset emails per account per hour
- [x] "Password changed" notice after reset and after change-password
- [x] SMTP sender (`app/services/email.py`) with STARTTLS / implicit TLS / login
- [x] Shared Dramatiq broker (`app/core/broker.py`), jobs in `app/jobs/`, per-job DB/Redis connections
- [x] Compose: backend services read `.env` (previously only a fixed list of variables reached them), `PUBLIC_URL`, optional `mailpit` profile
- [x] ADR 010: password reset

**Verification**:
- Ruff, ruff format, mypy (34 files) pass
- Pytest: 163 passed, 91% total coverage; password reset service and API 100%
- End to end with Mailpit through Caddy: request for an existing and an unknown address give identical `202` responses; exactly one email arrives, for the existing account; the link works once (`204`, then `400`); old password rejected, new one accepted; "password changed" email arrives; no email addresses or tokens in api, worker or Caddy logs

**Commit**: `feat: add password reset by email`

---

### Slice 0.7: Auth: OIDC
**Status**: Complete

**Deliverables**:
- [x] Documentation checked first (OIDC Core 1.0, RFC 9700, RFC 7636, Entra ID claims reference and discovery document, Authlib/joserfc, Caddy log filters); sources in ADR 011
- [x] OIDC client (`app/services/oidc.py`): discovery and JWKS caching with key-rotation refresh, authorization code flow with state, nonce and PKCE S256, `client_secret_post`/`basic`, full ID token validation (asymmetric algorithms only, iss/aud/azp/exp/iat/nonce/sub), HTTPS only, multi-tenant template issuer refused
- [x] `user_identities` table (migration `0004`): accounts matched on (issuer, subject), never email
- [x] Protocol-independent SSO account service (`app/services/sso.py`) ready for SAML; auto-provisioning (configurable); refuses sign-ins whose email belongs to an unlinked existing account
- [x] Endpoints: `GET /api/v1/auth/oidc`, `GET /api/v1/auth/oidc/login`, `GET /api/v1/auth/oidc/callback`; browser-bound, single-use transactions; no open redirects; errors as `/login?sso_error=<code>`
- [x] Caddy redacts `code` and `state` from access logs
- [x] `python-jose` (unused) replaced by `joserfc`
- [x] ADR 011: OIDC sign-in

**Not in this slice**: role mapping from claims (needs Slice 0.8), admin linking of existing accounts, provider logout, multi-tenant Entra.

**Verification**:
- Ruff, ruff format, mypy (38 files) pass
- Pytest: 220 passed, 91% total coverage. Tests run the whole flow against a fake provider that verifies PKCE, redirect URI and client credentials, and cover forged HS256 and `alg: none` tokens, key rotation, replay, login CSRF, account takeover by email and open redirects
- End to end in Docker against `navikt/mock-oauth2-server` through Caddy: redirect to the provider and back, account created as SSO-only with (issuer, subject), session works, replayed callback refused, `client_secret_basic` path used; Caddy logs show `code=REDACTED&state=REDACTED`

**Commit**: `feat: add OpenID Connect sign-in`

---

### Slice 0.8: Roles & Permissions
**Status**: Complete

**Deliverables**:
- [x] Permission catalogue and the 8 system roles from the brief in code (`app/core/permissions.py`)
- [x] `roles` and `role_assignments` tables (migration `0005`); system roles synced by `python -m app.cli sync-roles`, run by the `migrate` service
- [x] Scoped authorization (`app/services/authorization.py`): roles apply at their scope and below, never above or sideways; expiry; scope-type registry for curriculum scopes (Slice 0.9)
- [x] No privilege escalation: granting or removing a role needs `roles.assign` and all of the role's permissions at that scope; last platform admin protected
- [x] Custom roles (create, update, delete when unused); system roles read-only
- [x] `require_permission` dependency; service errors mapped to 403/422/409 centrally
- [x] Endpoints for permissions, roles, role assignments, user administration (create, list/search, get, rename, deactivate/reactivate) and `GET /auth/me/roles`
- [x] `python -m app.cli create-admin` bootstrap/recovery command
- [x] ADR 012: roles and scoped permissions

**Verification**:
- Ruff, ruff format, mypy (46 files) pass
- Pytest: 318 passed, 94% total coverage; authorization service 99%, role and user endpoints 100%
- Permission matrix: every system role at every scope type it allows, checked against every permission, plus checks that it does not reach parent or sibling scopes
- End to end in Docker: `migrate` synced all 8 roles; CLI created the platform admin; admin created a user and made them curriculum office for a faculty; that user was refused user listing and self-promotion to platform admin (403) but could see their faculty's assignments; deactivating them ended their session

**Commit**: `feat: add scoped roles and permissions`

---

### Slice 0.9: Curriculum Models
**Status**: Complete

**Deliverables**:
- [x] Models (`app/models/curriculum.py`): `QualificationType`, `Programme` (with SAQA ID, NQF exit level, CHE and professional council accreditation), `CurriculumVersion`, `Phase`, `Module`, `LearningEvent`, `Objective`, `ObjectiveLink`
- [x] Migration `0006` (schema) and data migration `0007` seeding the 10 HEQSF qualification types from the brief, each marked "verify against the current HEQSF"
- [x] Database integrity: check constraints (NQF 1-10, credits, minutes, academic year, objective owner matches level, enum values), composite FK keeping a module's phase in its version, partial unique indexes ignoring soft-deleted rows
- [x] Objective service (`app/services/curriculum.py`): level and version from owner; upward link rules (same version, broader level, session objectives link to their own module)
- [x] Real authorization scopes for programme, module and learning event (`app/services/curriculum_scopes.py`)
- [x] Curriculum factories
- [x] ADR 013: curriculum data model

**Not in this slice**: curriculum CRUD API and tree editor, publishing rules, copy-forward and version diff (phase 1); teaching format and taxonomy level columns arrive with tag lists and taxonomy scales.

**Verification**:
- Ruff, ruff format, mypy (49 files) pass; `alembic check` reports no drift; `0007` round-trips
- Pytest: 348 passed, 94% total coverage; curriculum models and scopes 100%, curriculum service 97%
- End to end in Docker: `migrate` applied `0006` and `0007`; a platform admin assigned programme director at a real programme through the API (201), and a non-existent programme was refused (422)

**Commit**: `feat: add curriculum models`

---

### Slice 0.10: Framework Models
**Status**: Complete

**Deliverables**:
- [x] Models (`app/models/framework.py`): `TaxonomyScale`, `TaxonomyLevel` (with verb lists), `Framework` (one row per version), `FrameworkItem` (tree with depth, position, metadata), `FrameworkCrossRef`, `Crosswalk`, `CrosswalkEntry`
- [x] `objectives.taxonomy_level_id` (deferred from Slice 0.9)
- [x] Migration `0008` with database integrity: key format, key + version unique among live rows, parent in same framework (composite FK), depth consistent with parent, crosswalk entry items consistent with type
- [x] Framework service (`app/services/frameworks.py`): add items, cross-references and crosswalk entries with validation; activating a version supersedes older ones
- [x] `str_enum` and `live_unique` model helpers moved to `app/models/base.py`
- [x] Test loading the shipped demo pack into the models
- [x] ADR 014: framework and taxonomy data model

**Not in this slice**: pack and Excel import, framework browser, cross-framework search (phase 1); the pack schema needs extending for crosswalks, tag lists and cross-framework references when the importer is built.

**Verification**:
- Ruff, ruff format, mypy (51 files) pass; `alembic check` reports no drift; `0008` round-trips
- Pytest: 373 passed, 95% total coverage; framework models and service 100%
- Docker: `migrate` applied `0008`; all seven framework and taxonomy tables present; `/ready` healthy

**Commit**: `feat: add framework and taxonomy models`

---

### Slice 0.11: Tag Models
**Status**: Complete

**Deliverables**:
- [x] Models (`app/models/tagging.py`): `TagList` (kind, applicable item types), `TagValue` (label, optional code), `Tagging` (one FK column per taggable type, `inherited_from_id`)
- [x] `learning_events.format_value_id`: teaching format from a teaching-method list (deferred from Slice 0.9)
- [x] Migration `0009` with database integrity: key format, live uniqueness of keys, labels and codes, exactly one tagged item, uniqueness per tag/item/source, cascades from items, values and source taggings
- [x] Tagging service (`app/services/tagging.py`): add values, tag items, remove direct tags (inherited ones go with their source), list an item's tags, set teaching format
- [x] ADR 015: tag lists and tagging

**Not in this slice**: inheritance rules and preview (with the tagging UI in phase 1); default tag lists (packs and demo dataset).

**Verification**:
- Ruff, ruff format, mypy (53 files) pass; `alembic check` reports no drift; `0009` round-trips
- Pytest: 391 passed, 95% total coverage; tagging models and service 100%
- Docker: `migrate` applied `0009`; tag tables and `learning_events.format_value_id` present

**Commit**: `feat: add tag lists and tagging`

---

### Slice 0.12: Mapping Models
**Status**: Complete

**Deliverables**:
- [x] Models (`app/models/mapping.py`): `AIRun`, `AIRunCall` (prompts and responses for audit), `MappingLink`, `ReviewAssignment`
- [x] Migration `0010` with database integrity: one link per objective and item, coverage 0-5, confidence 0-1, accept method set exactly when accepted, different first and second reviewers, token/cost/timing checks
- [x] Review workflow (`app/services/mapping.py`): starting status by source, accept / reject / second review, four-eyes mode, disagreement flag, reopen, bulk accept above a confidence threshold, evidence quote must come from the objective
- [x] `objective_scope()` for authorizing work on an objective's mappings and tags
- [x] ADR 016: mapping, AI run and review data model

**Not in this slice**: AI pipeline, review queue UI and endpoints, automatic acceptance, coverage reports (phase 1); framework version migration (phase 2).

**Verification**:
- Ruff, ruff format, mypy (55 files) pass; `alembic check` reports no drift; `0010` round-trips
- Pytest: 421 passed, 95% total coverage; mapping models and service 100%
- Docker: `migrate` applied `0010`; mapping tables present

**Commit**: `feat: add mapping, AI run and review assignment models` (9fce3b1)

**Follow-up** (`feat: mapping review policy and permanent AI runs`):
- [x] Institution mapping policy (`settings["mapping"]`): `four_eyes` and `second_review_for_rejects`, both off by default (`app/services/policies.py`)
- [x] Reopening limited to rejected links and to users with `mapping.review` at the objective's scope (audit entry added in Slice 0.13)
- [x] AI runs and calls can never be deleted (trigger, `RESTRICT`, AI links must name their run); retention clears prompt/response text (`AI_CALL_RETENTION_DAYS`, `purge-ai-content` command), keeping run records and counts
- [x] Migration `0011`; ADR 016 revised
- Verification: 431 tests pass, 96% coverage; mapping, policy and retention services 100%. In Docker, `0011` applied and a `DELETE` on `ai_runs` was refused by the database

---

### Slice 0.13: Audit Log Service
**Status**: Complete

**Deliverables**:
- [x] `audit_log` table (migration `0012`) with ordering `seq`, event-time `occurred_at`, actor, entity, action, before/after, context
- [x] Automatic capture of every change to `Audited` models (27 models) via a session hook, in the same transaction; personal fields excluded or recorded by name only
- [x] Actor from authentication (system for commands and jobs), per-request actor context middleware, `audit_operation` labels (mapping reopen records the reviewer and reason)
- [x] POPIA: admin views of user records recorded; deleting a user anonymises their audit entries
- [x] Append-only: trigger refuses updates and deletes except anonymisation and the retention purge (`AUDIT_LOG_RETENTION_DAYS`, `purge-audit-log` command)
- [x] `GET /api/v1/audit-log` with filters, `audit.view` permission
- [x] `activate_framework` changed to ORM updates so they are audited
- [x] ADR 017: audit log

**Verification**:
- Ruff, ruff format, mypy (61 files) pass; `alembic check` reports no drift
- Pytest: 454 passed, 96% total coverage; audit service 99%, audit API 98%
- End to end in Docker: role sync and CLI bootstrap recorded as system entries; user creation and user list view recorded with the admin as actor; no email addresses in audit entries; `UPDATE` and `DELETE` on `audit_log` refused by the database; deleting the test users anonymised their entries

**Commit**: `feat: add audit log`

---

### Slice 0.14: Terminology & Profiles
**Status**: Complete

**Deliverables**:
- [x] Terms, profiles and profile features in code (`app/core/profiles.py`): core always on, health adds role balance report, council evidence pack, clinical placements
- [x] Typed institution settings (`app/services/institution_settings.py`): terminology overrides, profiles, default taxonomy scale, mapping policy; section updates keep unknown keys; invalid values refused
- [x] `GET /api/v1/institution` (any signed-in user) and `PATCH /api/v1/institution/settings` (`settings.manage`), audited
- [x] Default English wording for every term in `frontend/src/i18n/locales/en.json` (`terms.<term>_one/_other`), with a test that backend terms and translations match
- [x] ADR 018: terminology and feature profiles

**Verification**:
- Ruff, ruff format, mypy (64 files) pass; frontend lint, typecheck and tests pass
- Pytest: 479 passed, 96% total coverage; settings service and profiles 100%, institution API 97%
- End to end in Docker: admin renamed "module" to "Course" and enabled the health profile; `GET /institution` returned the override and the three health features; the change appeared in the audit log

**Commit**: `feat: add configurable terminology and feature profiles`

---

### Slice 0.15: Frontend Scaffold
**Status**: Complete

**Deliverables**:
- [x] API client (`src/api/`): axios with session cookie and CSRF header, typed endpoints, `ApiError`, central query keys
- [x] Session (`src/session/`): current user, roles and permissions (with server-side implications)
- [x] Institution provider (`src/institution/`): loads settings, applies terminology overrides to i18next, `useFeature()`
- [x] App shell (`src/layout/`): Mantine AppShell, responsive navbar, light/dark toggle, user menu with sign-out, skip link
- [x] Navigation by permission (brief section 11): staff sections per permission, students see Explorer and Search only; direct addresses to hidden sections show "No access"
- [x] Routes (`src/routes/`): auth guard with sign-in redirect, start page, placeholders, not-found, no-access, error with retry
- [x] Backend: role summaries include their permissions (`/auth/me/roles`)
- [x] All UI text in `en.json` (`layout.*`, `pages.*`)
- [x] ADR 019: frontend architecture

**Verification**:
- Frontend lint, typecheck, production build pass; 20 tests (86% line coverage): API client, navigation rules, terminology, routing and guards
- Backend: ruff, mypy pass; 479 tests pass
- Docker: Caddy and nginx serve the app for client-side routes (`/`, `/explorer`, deep paths); hashed assets cached as immutable; same-origin API reachable

**Commit**: `feat: add frontend scaffold`

---

### Slice 0.16: Frontend Auth
**Status**: Complete

**Deliverables**:
- [x] Sign-in page: email/password, SSO button when enabled, `sso_error` messages, rate-limit wait time, slow sign-in note, safe `next` redirect
- [x] Forgotten password page (same confirmation either way) and reset page (token from the URL fragment, removed from the address bar)
- [x] Account page with change password; SSO-only accounts get an explanation
- [x] Backend: public `GET /api/v1/auth/options` (password rules, SSO availability) and `has_password` on `/auth/me`
- [x] `SuccessNotice` for polite status announcements; translated strings for every message
- [x] Library code split into cached chunks (app code about 10 kB gzipped)
- [x] ADR 019 extended

**Verification**:
- Frontend lint, typecheck and build pass; 49 tests (90% line coverage) including sign-in, redirects, SSO, errors, reset and account flows
- Backend: ruff, mypy pass; 481 tests pass
- Docker: sign-in, reset and account pages served; `/auth/options` reachable without signing in

**Commit**: `feat: add sign-in, password reset and account pages`

---

### Slice 0.17: First-Run Setup Wizard
**Status**: Complete

**Deliverables**:
- [x] Setup token derived from `SECRET_KEY`, printed in the API log while setup is pending and shown by `python -m app.cli setup-token`
- [x] `GET /api/v1/setup/status` and `POST /api/v1/setup`: once only (advisory lock, re-check), all or nothing (savepoint), rate limited, audited as `setup.complete`, admin signed in immediately
- [x] Creates the institution (name, short code, country, optional health profile), the first admin and the `platform_admin` role
- [x] `/setup` wizard (institution with token, administrator, confirm); sign-in page sends visitors there while setup is pending
- [x] Shared `too_many_attempts` 429 helper
- [x] ADR 020: first-run setup

**Verification**:
- Backend: ruff, mypy pass; 496 tests pass, 96% coverage; setup service and API 100%
- Frontend: lint, typecheck, build pass; 55 tests (91% line coverage)
- Fresh install in Docker (new compose project, empty volumes): migrations ran, the API log and CLI showed the setup token; wrong token refused (403); setup with the token created the institution with the health profile and a signed-in platform admin; status then reported done; a second attempt was refused (409); the CLI and a restarted API no longer offered the token; audit entries recorded under `setup.complete`

**Commit**: `feat: add first-run setup wizard`

---

### Slice 0.18: Demo Dataset
**Status**: Complete

**Deliverables**:
- [x] Framework pack validation and import (`app/services/packs.py`): unique codes, known parents, no cycles, valid cross-references and scales; reuses existing scales
- [x] Demo framework pack rewritten to match the brief: 8 items in 2 levels, fictional text, Bloom (revised) and Miller scales; bundled copy in the backend kept identical by a test
- [x] Demo curriculum data (`app/demo/data/bsc-health-sciences-demo.json`): BSc Health Sciences (Demo), 3 modules (one longitudinal), 20 sessions, 60 objectives (6 programme, 12 module, 42 session) linked upward with domains and Bloom levels, 3 tag lists, 13 accepted mappings
- [x] Loader (`app/demo/loader.py`) and `python -m app.cli load-demo`: one transaction, normal services, audited as `demo.load`, reuses the institution, framework and tag lists, refuses a second load
- [x] ADR 021: demo dataset and framework pack import

**Not in this slice**: a command to remove the demo; the fictional gold mapping set for the AI evaluation harness (phase 1).

**Verification**:
- Ruff, ruff format, mypy (69 files) pass
- Pytest: 515 passed in 3 min 19 s, 96% total coverage; pack importer 100%, demo loader 97% (demo checks merged into fewer loads, cutting the run from 5 min 25 s)
- End to end in Docker: setup through the API, then `load-demo` created 3 modules, 20 sessions, 60 objectives, 56 upward links, 13 mappings and the Bloom and Miller scales; a second run reported the demo already loaded

**Commit**: `feat: add demo dataset and framework pack import`

---

### Slice 0.19: Documentation Skeleton
**Status**: Complete

**Deliverables**:
- [x] MkDocs Material site (`mkdocs.yml`, `docs/requirements.txt` pinning MkDocs 1.6.1 and Material 9.8.0, own `.venv-docs`); home page, ADR index
- [x] Operations guides: install (fresh Linux server, DNS, certificates, setup wizard, troubleshooting), configuration reference, upgrade (with rollback), backup and restore (schedule, off-site copies, restore test, new-server recovery)
- [x] Administration guides: admin basics (terminology, profiles, mapping policy, audit log, retention, monitoring, CLI), users and roles (API with `curl`/`jq` until the admin screens exist, admin recovery), single sign-on (OIDC, Entra ID)
- [x] `deploy/backup.sh` (`pg_dump` custom format, verified, owner-only, 14-day retention), `deploy/restore-test.sh` (restores into a scratch database, prints row counts), `deploy/restore.sh` (restores into a side database first, then swaps; flushes Redis; migrations upgrade older backups)
- [x] Local deployment changes that survive upgrades: `deploy/caddy/*.caddy` imported into the Caddy site (e.g. own certificate), `deploy/docker-compose.override.yml`; both git-ignored
- [x] `/ready` returns HTTP 503 when the database or Redis is down (was 200 with `not_ready`)
- [x] CI `docs` job (`mkdocs build --strict`); `docs.yml` publishes `main` to GitHub Pages
- [x] README quick start and docs links fixed; CONTRIBUTING (docs, Node 22) and CLAUDE.md updated; stale `scripts/seed_demo.py` stub removed (`load-demo` replaces it)
- [x] ADR 022: documentation site and backups

**Not in this slice**: user guides per role, glossary and FAQ (with the Phase 1 screens); AI provider and Brightspace setup guides (Phases 1 and 2); POPIA data inventory (`docs/privacy/`).

**Verification**:
- `mkdocs build --strict` passes (links and anchors checked); Zensical 0.0.72 also builds the same config without issues
- Ruff, ruff format, mypy (69 files) pass; pytest 515 passed, 96% coverage
- Shellcheck clean on the three scripts
- Install guide followed on a fresh compose project (copy of the tree, empty volumes, ports moved with the documented override file): `.env` commands, `up -d --build --wait` (all services as described, `migrate` exited 0), `/ready`, setup token, setup, `load-demo`
- Every API command in the users-and-roles and admin-basics guides run verbatim in a Linux container with `bash`, `curl` and `jq`
- Backup and restore test on the demo data (3 modules, 20 sessions, 60 objectives, 13 mappings); a truncated dump that passes `pg_restore --list` was refused by `restore.sh` with live data and services untouched; a real restore removed a user created after the backup, ended existing sessions (401) and left the site ready
- Own certificate in `deploy/caddy/` served by Caddy; `/ready` answered 503 with the database stopped
- Not verified here: a real Linux server with public DNS and Let's Encrypt (Phase 0 definition of done)
- GitHub Actions for 3e212d4: CI green (all jobs including the new Documentation job); the Docs publish workflow built the site but stopped at `configure-pages` because Pages is not enabled for the repository yet

**Commit**: `feat: add documentation site, install guides and backup scripts` (3e212d4)

---

### Slice 0.20: CLAUDE.md & PROGRESS.md Finalization
**Status**: Complete

**Deliverables**:
- [x] CLAUDE.md checked against the code: every module, helper and fixture it names exists; backend and frontend layout added; frontend example used a translation key that does not exist (now a `terms.*` example); Playwright marked as not set up yet; frontend file naming matches the code (components PascalCase, other modules camelCase); status codes 202/409/429/503 added; conventions for registering routers, adding settings and CLI commands, recording personal-data views; slice workflow and current status
- [x] PROGRESS.md: Phase 0 summary, Definition of Done with evidence, and every deferred item in one list

**Verification**: documentation changes only; `mkdocs build --strict` passes.

**Commit**: `docs: finalise CLAUDE.md and PROGRESS.md for phase 0`

---

### Slice 0.21: Phase 0 Gaps from the Brief
**Status**: Complete

**Deliverables**:
- [x] Dependabot: weekly grouped updates for backend and docs pip, frontend npm, Dockerfiles, compose file and GitHub Actions
- [x] CodeQL workflow (Python, JavaScript/TypeScript, Actions; `security-extended`): fails on any error or warning and keeps the SARIF as an artifact, because code scanning is not enabled on the private repository; uploads to code scanning when `CODE_SCANNING_ENABLED=true`
- [x] Release workflow: `vX.Y.Z` tags run CI, then push `ghcr.io/openaudire/ocmp-backend` and `ocmp-web` (version, `X.Y`, `latest`, sha); manual runs build without pushing; CI made callable (`workflow_call`); compose reads `OCMP_BACKEND_IMAGE` / `OCMP_WEB_IMAGE`; upgrade guide covers released images
- [x] POPIA: `docs/privacy/data-inventory.md` (every personal data field in the database, Redis, logs, backups and outbound flows, with purpose and retention; data subject rights today) and `docs/privacy/privacy-notice-template.md` (POPIA section 18 contents)
- [x] Container log rotation (5 x 10 MB per service): Docker's default kept logs with client IP addresses without limit
- [x] Embeddings: **kept as an optional profile, off by default, no image built** (nothing uses embeddings before Phase 1). Image name points at its future GHCR location (`OCMP_EMBEDDINGS_IMAGE` overrides), compose comment and configuration guide say it is not available, `EMBEDDINGS_LOCAL` now defaults to `false`
- [x] ADR 023; CLAUDE.md rules for the data inventory, CodeQL findings and releases

**Verification**:
- Ruff, ruff format, mypy pass; config default test updated; `mkdocs build --strict` passes
- Dev stack recreated with the new compose file: all services healthy, containers use the rotating json-file log options; `docker compose config` lists no `embeddings` service unless its profile is given
- GitHub Actions on `764d194`: CI green; CodeQL green for Python, JavaScript/TypeScript and Actions; release workflow dry run (manual) ran CI and built both images without pushing; all six Dependabot update jobs succeeded and opened 8 pull requests (left for review: Mantine 7 to 9, react-i18next 15 to 17, Node 26 image and others are major upgrades)
- CodeQL fixes on the way: the job needed `actions: read` on a private repository (`d4842d9`); the Actions analysis then found 14 warnings, fixed by explicit `permissions` in CI and SHA-pinned third-party actions (`764d194`)
- Not verified: pushing images on a real tag (no release was tagged); the Docs publish workflow still stops because GitHub Pages is not enabled

**Commits**: `ci: add Dependabot, CodeQL and release images; add POPIA records` (8cc9376), `ci: give CodeQL read access to workflow runs` (d4842d9), `ci: pin third-party actions and limit CI token permissions` (764d194)

---

### Install Guide Rehearsal
**Status**: Complete

`docs/operations/install.md` followed literally, as a new technician, on a fresh stand-in server: an Ubuntu 24.04.5 container with a normal `sudo` user, Docker Engine installed from Docker's current official instructions (Docker 29.x, Compose v5.6.1), a fresh clone of `main` (d7b8e36) into `/opt/ocmp`, DNS simulated with `/etc/hosts`, and a Mailpit container standing in for the institution's SMTP server.

**Worked as written**: Docker checks and the `docker` group; `.env` commands (secrets generated, file mode 600); `up -d --build --wait` (4.5 minutes on 8 CPUs; services as described); own certificate from an institution CA; setup token; setup; password reset email with the right link (`PUBLIC_URL` default); a comment left after `SMTP_TLS=false` is ignored; backup (owner-only file), the cron command line, restore test; demo load; token refused after setup; the troubleshooting text for a missing `SECRET_KEY` matches Compose's message.

**Fixed in the guide**:
- Cloning failed at a username prompt: the repository is private and the guide did not say so. Added the need for repository access and a read-only fine-grained token, and what to type at the prompt (also in the upgrade guide)
- On a server Let's Encrypt cannot reach, step 5's own check failed with `curl: (35) ... tlsv1 alert internal error`, and the certificate instructions came only after the setup wizard. Step 4 now asks the technician to choose the certificate route and put an own certificate in place before the first start (re-tested: works without a restart); troubleshooting explains curl errors 35 and 60
- Named the tools the guide uses (`git`, `curl`, `openssl`, an editor) and the Ubuntu releases Docker supports
- Compose version check: "v2.24 or later; current releases are v5.x"
- Email settings for port 465, an unencrypted internal relay and servers without sign-in
- `curl --resolve` for servers that cannot resolve their own name (re-tested)
- Docker opens ports 80/443 in the host firewall itself, even with `ufw`

**Not covered**: the setup wizard was submitted with the same request its page sends, because the stand-in server has no browser (the page itself was served, and the wizard UI was tested in Slice 0.17); `systemctl` steps (the container has no systemd, so Docker was started with `service`); cron scheduling itself (the command line was run by hand).

**Deferred**: the real public-server test (public DNS, inbound internet access, Let's Encrypt certificate) is deferred until a pilot server is available.

---

### Public-Repository Docs, Secret Scan and Image Visibility
**Status**: Complete

- [x] Install and upgrade guides written for the public repository (clone and pull need no account); a short note covers private copies (fine-grained token with read-only Contents access); released images described as public, with `docker login ghcr.io` only for private images
- [x] **Secret scan of the whole history** (33 commits, all refs):
  - gitleaks 8.30.1: 4 findings, all the same test placeholder `test-secret-key-that-is-at-least-32-characters-long` in `backend/tests/conftest.py` and `test_health.py` (false positives)
  - TruffleHog 3.99.7 (verified, unknown and unverified results): 0 findings
  - No `.env` file was ever committed (`deploy/.env` is git-ignored); the local `SECRET_KEY`, `POSTGRES_PASSWORD` and the GitHub CLI token appear in no commit
- [x] **Release image visibility** (GitHub packages documentation, checked 2026-10-25): images published by the release workflow take the repository's visibility when each package is first created and do not follow later changes. Tagged while the repository is private, they would be private and stay private after it goes public, until switched to public in each package's settings (irreversible). No image has been published yet (the dry runs do not push). `OpenAudire` is a personal account, so no organisation policy restricts public packages. Recorded in ADR 023 and CLAUDE.md

**Not verified**: cloning without credentials, which only works once the repository is public (see the checklist below).

---

## Before the Public Release

1. Make the repository public
2. From a machine without GitHub credentials, run the install guide's `git clone` (anonymous clone)
3. Enable GitHub Pages (source: GitHub Actions), set the repository variable `PAGES_ENABLED=true` (until then the Docs workflow only builds the site and skips publishing) and re-run the Docs workflow
4. Set the repository variable `CODE_SCANNING_ENABLED=true` (code scanning is free for public repositories)
5. Tag the first release only after step 1; check that `ghcr.io/openaudire/ocmp-backend` and `ocmp-web` are public (otherwise set each to public in its package settings), and pull one without signing in
6. Install on the pilot server with public DNS and Let's Encrypt (Phase 0 definition of done)

---

## Phase 0 Summary

Built in 20 slices plus a CI fix. The platform installs with Docker Compose, runs a
first-run setup wizard, signs people in with local accounts (Argon2id, sessions, CSRF,
throttling, password reset) or OpenID Connect, enforces scoped roles in the API, holds
the full curriculum, framework, tagging and mapping data model with an append-only audit
log, supports institution terminology and profiles, loads a fictional demo programme with
one command, and has operator and admin documentation with tested backup and restore
scripts.

| Area | State at the end of Phase 0 |
|---|---|
| Backend | 69 modules, 515 tests, 96% coverage, ruff/mypy strict clean |
| Frontend | App shell, sign-in, password reset, account, setup wizard; 55 tests, 91% line coverage |
| Database | 12 migrations, 30 tables, `alembic check` drift test |
| Decisions | ADR 001-023 |
| Docs | MkDocs site: install, configuration, upgrade, backup/restore, admin basics, users and roles, SSO |

### Deferred to later phases

Collected from the slices above so nothing is lost:

- **Phase 1**: curriculum CRUD API and tree editor, publishing rules, copy-forward and version diff; framework pack and Excel import, framework browser, cross-framework search (pack schema to extend for crosswalks, tag lists and cross-references); tag inheritance rules and tagging UI; AI pipeline, review queue, coverage reports; eval harness with a fictional gold set; admin screens for users, roles and settings (API only today); user guides per role, glossary, FAQ, AI provider setup guide; a command to remove the demo data; Playwright end-to-end tests; personal API tokens (`ApiToken`)
- **Phase 2**: SAML (account service is protocol-independent), framework version migration, Brightspace connector and setup guide; move to Node 26 LTS early in Phase 2 (CI, web image, CONTRIBUTING, `@types/node`; decided at Slice 1.0)
- **SSO**: role mapping from claims, admin linking of existing local accounts, provider logout, multi-tenant Entra
- **POPIA**: per-user data export and deletion, email address changes (the inventory and notice template exist since Slice 0.21)
- **CI/CD**: first tagged release, GitHub Pages and code scanning upload (see "Before the Public Release"); multi-architecture images
- **Deployment**: the embeddings image (optional profile, off by default) is built with the Phase 1 search features; move the docs from MkDocs Material (end of life 5 May 2027) to Zensical once it is stable
- **Security (later security slice)**: add a Content-Security-Policy header in Caddy (none is set today). Start in report-only mode, then enforce: `default-src 'self'`, no inline scripts (the colour-scheme bootstrap is already an external file, `public/color-scheme.js`), `style-src` allowing Mantine's inline style attributes, `font-src 'self'` (fonts are self-hosted), `connect-src 'self'`, `frame-ancestors 'none'`, plus the OIDC provider's address only where redirects need it. Check every screen with the Playwright suite while the policy is in report-only mode (recorded at Slice 1.1)

---

### CI fix and Node 22
**Status**: Complete

- [x] CI's backend lint job installed only ruff, mypy, pydantic and sqlalchemy and ran `mypy app --ignore-missing-imports`, so every other library became `Any` and strict mode failed with 45 errors on every commit. It now installs the project with dev extras and runs plain `mypy app` (settings from `pyproject.toml`), like local development (`cd8e46f`)
- [x] CI green on GitHub Actions for `cd8e46f`
- [x] CI and the frontend Docker image moved from Node 20 (end of life April 2026) to Node 22; the web image builds and serves on `node:22-alpine`

---

## Phase 0 Approval and Decisions (2026-10-25)

**Phase 0 is approved** by the project owner, with the public-server install deferred (below).

| # | Topic | Decision |
|---|---|---|
| 1 | Licence | Apache-2.0 confirmed; recorded in ADR 024 |
| 2 | Public repository | Go public before the first release; the owner chooses the timing ("Before the Public Release" steps 1-5) |
| 3 | Pilot server | Not chosen yet; the public-server install (DNS + Let's Encrypt) stays on the checklist (step 6) |
| 4 | Dependency upgrades | **Slice 1.0** comes before other Phase 1 work, so new screens are built on current versions: major upgrades (Mantine 7 to 9, react-i18next 15 to 17, GitHub Actions majors, `eslint-plugin-react-refresh` 0.4 to 0.5) with tests green, and Node moved to the **current LTS release**, not simply the newest. Minor/patch updates are merged as soon as CI passes |
| 5 | GitHub Pages | Enable after the repository is public (checklist step 3) |
| 6 | Docs tooling | MkDocs Material reaches end of life on 5 May 2027. Revisit Zensical when it has a stable release, well before May 2027 (ADR 022) |

Dependabot pull requests at approval: only #1 (Mailpit v1.21 to v1.31, development profile) was minor/patch; the others are majors for Slice 1.0. #8 bundled six GitHub Actions majors because the actions group had no update-type filter; the group now takes minor/patch only, so majors arrive as separate pull requests.

---

## Phase 0 Definition of Done

- [ ] Fresh Linux server with Docker can be set up by following install guide: rehearsed end to end on a fresh Ubuntu 24.04 stand-in server, with the guide fixed (see "Install Guide Rehearsal"); **the real public-server test (DNS + Let's Encrypt) is deferred until we have a pilot server**
- [x] CI is green (764d194: CI and CodeQL)
- [x] Demo data loads with one command
- [x] Role permissions covered by tests

---

## Decisions to review

Decisions made during the slices without asking first, following the brief and earlier
ADRs. Each can be changed; the "How hard" column says how much work that would be and the
last column records the owner's review. **Reviewed 2026-10-26: every earlier decision is
approved except the three marked "Changed" below (ADR 032).**

| Slice | Decision | Why | How hard to reverse | Review |
|---|---|---|---|---|
| 1.3, replaced in 1.5 | ~~Published versions stay editable until Slice 1.5~~ Only draft versions are editable; published and archived are read-only (ADR 030). The demo now has a 2027 draft to edit | The publishing rules arrived with 1.5 | Easy: one constant (`EDITABLE_STATUSES`) | Approved 2026-10-26 |
| 1.3 | Phases, adding and deleting modules, and moving a module to another phase need `curriculum.edit` at the programme; a module's own fields and its sessions need it at the module; a session's fields at the session | Brief section 4: directors own the structure, coordinators their modules and sessions | Easy: scope per endpoint | Approved 2026-10-26 |
| 1.3 | Deleting is a soft delete that takes the children with it (module: its sessions and all their objectives; session: its objectives), with one shared timestamp | Keeps later reports and copy-forward from seeing orphaned objectives; a restore can bring back what went together | Medium: data already deleted this way would need a restore step | Approved 2026-10-26 |
| 1.3 | A phase holding modules cannot be deleted (the dialog explains why) | Avoids deleting many modules by accident | Easy | Approved 2026-10-26 |
| 1.3 | Module codes are unique per version ignoring upper/lower case (the database index is case-sensitive) | "hsc101" and "HSC101" in one version would confuse imports and reports | Easy | Approved 2026-10-26 |
| 1.3 | Write endpoints answer 404 for items the user cannot see and 403 for visible items they may not change | Same rule as the read API (ADR 027): the API does not reveal what exists | Easy | Approved 2026-10-26 |
| 1.3 | Add, Edit and Delete buttons sit in the details panel of the selected item, not one "+ Add learning event" button under the tree as in the mockup | Every action sits next to the item it changes, and the same pattern works for phases, modules and sessions | Easy (UI only) | Approved 2026-10-26 |
| 1.3 | New items go to the end of their parent; reordering waits for Slice 1.4 | Matches the plan | Easy | Approved 2026-10-26 |
| 1.3 | `require_permission` scope resolvers are now async and receive the database session and the user | Curriculum scopes need a lookup (version to programme) and a visibility check | Easy: no other endpoint used `scope=` yet | Approved 2026-10-26 |
| 1.3 | The request's database session now commits when the endpoint returns, before the response is sent (`Depends(..., scope="function")`) | Found by the new end-to-end journey: FastAPI ended `yield` dependencies after the response, so a read straight after a save could miss it, and a failed commit still answered 2xx | Easy: one line in `app/core/database.py` | Approved 2026-10-26 |
| 1.3 | Filled red (delete) buttons use the on-brand text colour, like filled brand buttons | White text on the dark theme's light red failed contrast (axe) | Easy | Approved 2026-10-26 |
| 1.4 | Moving phases and modules (order and copy) needs `curriculum.edit` at the programme; moving and copying sessions needs it at the module, so a lecturer cannot reorder or copy their own session | Same split as adding and deleting in 1.3 (ADR 028) | Easy: scope per endpoint | Approved 2026-10-26 |
| 1.4 | Reorder API takes the new index among siblings (`POST .../move {"position": n}`), not a full ordered list | One small request per move; a change elsewhere in the list does not make it fail | Easy | Approved 2026-10-26 |
| 1.4 | Drag and drop moves items only among their siblings; a module changes phase through Edit | Keeps the drop rules simple and matches the 1.3 phase-move permission | Easy (UI and one endpoint) | Approved 2026-10-26 |
| 1.4 | Native browser drag and drop, no library; keyboard and single-pointer path is Move up / Move down buttons in the details panel | The tree is our own ARIA tree; library keyboard sensors would compete with its arrow keys; WCAG 2.5.7 is met by the buttons | Easy: a library can replace the events, the API stays | Approved 2026-10-26 |
| 1.4 | A copy goes right after the original; sessions are copied only within their module | Avoids broken upward links (a session objective links to its own module's outcomes) | Easy | Approved 2026-10-26 |
| 1.4 | Copies take children, objectives (with status), upward links (remapped inside the copy) and tags; not framework mappings, role assignments or the LMS reference | Mappings are reviewed decisions about one objective and would double coverage; access and LMS links belong to the original | Medium: copies made so far would need their mappings added by hand | Approved 2026-10-26 |
| 1.4 | Copying a phase asks for a new code for each of its modules (no generated codes); the name defaults to "<name> (copy)" | Codes are meaningful and unique per version; the user chooses them | Easy (UI) | Approved 2026-10-26 |
| 1.4 | The long e2e journeys are marked `test.slow()` | With two more journeys in parallel, the 1.3 editing journey passed 30 s locally | Easy | Approved 2026-10-26 |
| 1.5 | A published version can be returned to draft (and an archived one published again) by people with `curriculum.publish`; archiving is one more step from published | Lets a mistake in a published year be corrected without copying the whole year; students stop seeing it meanwhile | Easy: the `TRANSITIONS` table | Changed 2026-10-26 (ADR 032): needs `curriculum.unpublish` and a written reason |
| 1.5 | Publishing needs at least one module | An empty version should not reach students | Easy | Approved 2026-10-26 |
| 1.5 | Only drafts can be deleted (soft delete with contents, one timestamp); needs `curriculum.edit` | Published history must not vanish; drafts made by mistake can go, and the year becomes free | Easy | Approved 2026-10-26 |
| 1.5 | Per-item lineage: nullable `based_on_id` (self reference, `ON DELETE SET NULL`, indexed) on phases, modules, learning events and objectives, set by copy forward only (migration 0013) | The diff and later reports follow items across years even when renamed; additive, no data rewritten, clean downgrade | Medium: dropping the columns is simple, but the diff then falls back to matching by name and code | Approved 2026-10-26 |
| 1.5 | Copy forward also copies framework mappings with their review state, unlike a single-item copy (ADR 029); LMS references are not copied | A new year continues the same curriculum; a copy of one item would double coverage | Easy: one function (`_copy_mappings`); mappings already copied would need removing by hand | Approved 2026-10-26 |
| 1.5 | Copy forward keeps module codes and the order; the new year is chosen by the user (suggested: newest + 1), must be free | Codes are unique per version, so no clash | Easy | Approved 2026-10-26 |
| 1.5 | Copying roles needs `roles.assign` and every permission of each role (the assign rule); people without it get no names in the preview and copy the structure only | The preview shows holders' display names; the assign rule keeps escalation out | Easy | Approved 2026-10-26 |
| 1.5 | Version diff matches by lineage first, then by phase name, module code, session title and objective text; order, upward links, tags and mappings are not compared | Keeps the first diff readable; the rest can be added later | Easy | Approved 2026-10-26 |
| 1.5 | Only whole-visible versions of one programme can be compared; the UI offers "Compare versions" to people who see the whole version | Narrow roles see parts of versions only | Easy | Approved 2026-10-26 |
| 1.5 | Running `load-demo` on an install that has only the published demo version adds the 2027 draft instead of refusing; the draft is made by copy forward plus a few scripted changes | Existing trial installs get the new demo content without a reset | Easy | Approved 2026-10-26 |
| 1.6 | Objectives are edited with `objectives.edit` (not `curriculum.edit`) at the scope that owns them: programme for programme outcomes, module for module outcomes, session for session objectives (ADR 031) | The permission already exists and matches the brief (lecturers edit their own session objectives, coordinators their module's outcomes) | Easy: scope per endpoint | Approved 2026-10-26 |
| 1.6 | A person can choose upward links only to outcomes they can see (programme outcomes need the whole version, module outcomes the module); links to outcomes they cannot see stay untouched when they save | Keeps the read rules of ADR 027 (no widening of what a lecturer sees); a lecturer with only a session role cannot choose links yet | Easy: one function (`parent_options`) widens the list | Changed 2026-10-26 (ADR 032): read-only sight of programme and own-module outcomes for link choosing |
| 1.6 | A session objective may link to its own module's outcomes or directly to programme outcomes; a module outcome only to programme outcomes | Matches the existing `link_objectives` rule; traceability works either way | Easy | Approved 2026-10-26 |
| 1.6 | Any editor may set an objective's status (draft, approved, retired); there is no approval permission | The brief has no approval step for objectives; quality checks arrive in 1.7 | Easy to restrict later | Changed 2026-10-26 (ADR 032): draft and ready for review for editors, approving needs `objectives.approve` |
| 1.6 | The taxonomy level selector offers the levels of all scales (grouped by scale), not only the institution's default scale | The data model holds one level per objective; the default scale may be Bloom or Miller or a combined scale | Easy | Approved 2026-10-26 |
| 1.6 | Objective text is limited to 2000 characters; programme and module objectives are called "outcomes" in the UI text, session objectives use `terms.objective` | Longer text is a sign of several objectives in one; the existing screens already say "outcomes" | Easy | Approved 2026-10-26 |
| 1.6 | Objectives are added at the end; reordering and moving an objective to another session are not part of this slice | The plan lists upward links, domain and level only | Easy: a move endpoint like ADR 029 | Approved 2026-10-26 |
| 1.6a | Narrow roles (session or module only) read the programme outcomes and their own module's outcomes as link options only; the outcome list, module details and structure stay hidden | Owner decision: lecturers must be able to pick upward links; nothing else above their scope opens (ADR 032) | Easy: `parent_options` |  Owner decision 2026-10-26 |
| 1.6a | New status `ready_for_review` (check constraint widened in migration 0014); approved and retired (and leaving them) need the new permission `objectives.approve` (module coordinator and above) | Owner decision: lecturers draft, coordinators approve | Easy: one set of statuses and the permission |  Owner decision 2026-10-26 |
| 1.6a | A lecturer who rewords an approved objective sends it back to ready for review; a retired objective's wording needs the permission | Keeps the approval meaningful without blocking typo fixes entirely | Easy: `update_objective` |  Decided in 1.6a, to review |
| 1.6a | No data migration for the new permissions: system roles are synced from code by `sync-roles`, which the `migrate` service runs after `alembic upgrade` (ADR 012) | A data migration would duplicate that and drift from the catalogue | Easy |  Decided in 1.6a, to review |
| 1.6a | `curriculum.unpublish` is held by curriculum office, programme director and platform admin; unpublishing needs both it and `curriculum.publish`; the reason is trimmed, 1 to 500 characters, stored as the `reason` of the audit operation | Owner decision (programme director and a written reason) | Easy |  Owner decision 2026-10-26 |
| 1.6a | `mapping_links.needs_recheck` (boolean) is set on accepted links when the objective wording changes; cleared by `confirm_recheck` (needs `mapping.review`) or by reopening; copy forward keeps it. Suggested, rejected and second-review links are not flagged. No HTTP endpoint to confirm yet | Owner decision: accepted links stay accepted but are marked; mapping endpoints and reports come later | Easy: drop one column; reports must show the flag |  Owner decision 2026-10-26 |
| 1.6a | The migration downgrade turns `ready_for_review` objectives back into drafts with a plain `UPDATE` | The old check constraint cannot hold the new value; downgrades are for local use | Easy |  Decided in 1.6a, to review |
| 1.6a | The e2e lecturer account `e2e.lecturer@example.org` is made through the admin API and kept between runs; its password is the admin test password plus `-lecturer` | Sign-in is rate limited, so it signs in once like the admin; no extra secret | Easy |  Decided in 1.6a, to review |
| 1.7 | Checker is rule based and advisory: findings never block saving, nothing is stored (`detected_verb` and `quality_flags` stay unused) and nothing goes to an AI provider (ADR 033) | Brief: rule-based first; stored flags would go stale when links or verb lists change | Easy: a job could fill the columns later |  Decided in 1.7, to review |
| 1.7 | Verb lists per level stay in `taxonomy_levels.verbs` (pack format); only wording rules and extra verbs are in a versioned per-language JSON file (`objective_rules/en.json`) | One source for level verbs; no copy in code to drift | Easy |  Decided in 1.7, to review |
| 1.7 | Severities: warning for vague verb, several verbs, over 40 words, no domain, no upward link; note for the rest (no known verb, under 3 words, lead-in wording, hard-to-measure words, level differs from verb) | Brief lists the first group as flags; the rest are style advice | Easy: one table and the data file |  Decided in 1.7, to review |
| 1.7 | Live check needs `objectives.edit` at the owner's scope (three endpoints), is limited to 240 a minute per user (Redis counter on a hashed user id, in the data inventory); the list needs `objectives.edit` anywhere and shows only visible, non-retired objectives | Same rule as adding an objective; the list reveals nothing beyond ADR 027 | Easy |  Decided in 1.7, to review |
| 1.7 | A suggested level is shown as a button and set only on click; a verb in several levels or scales lists each | Never auto-applied | Easy |  Decided in 1.7, to review |
| 1.7 | Bulk list is a page `/curriculum/versions/:id/quality` opened by a Check wording button in the version bar for people holding `objectives.edit` | Same pattern as Compare versions | Easy (UI) |  Decided in 1.7, to review |
| 1.8 | Tagging is offered on modules, sessions and objectives (programme, module and session level); programmes themselves are not taggable from the UI or API (ADR 034) | A programme is not a versioned item, so its tags would not follow copy forward; the model still allows it | Easy: one more path kind |  Decided in 1.8, to review |
| 1.8 | Inheritance: a module's tag can go to its sessions; an objective's tag to the objectives linked beneath it, at any depth. It is chosen when tagging, shown first in a preview of every item reached, and applied once: items linked or added later are not tagged | Brief: always preview every affected item before saving; keeps the effect visible and reversible | Medium: re-applying to later links would need an action on the source |  Decided in 1.8, to review |
| 1.8 | The "Also give this tag to the N items" box is ticked by default when any item would be reached | The preview is on screen above the button; passing tags down is the point of the feature | Easy (UI) |  Decided in 1.8, to review |
| 1.8 | Every inherited tagging points to the direct tagging it came from, even through several levels; an item with the tag from two sources shows it once with both sources; an item that has the tag directly is skipped | Removing the source removes everything it passed on; the source named is the item that was tagged | Easy |  Decided in 1.8, to review |
| 1.8 | Only direct tags are removed (422 for inherited); removing one deletes its inherited rows through the ORM so each is in the audit log | Brief: record the inheritance source; CLAUDE.md audit rule (database cascade alone is not audited) | Easy |  Decided in 1.8, to review |
| 1.8 | A tag list's key and kind cannot change; a list or tag in use (tagged, or a session's format) cannot be deleted (409) and is made inactive instead; deleting an unused list deletes its tags | Imports use the key, teaching-method lists back session formats, and history must not lose tags | Easy |  Decided in 1.8, to review |
| 1.8 | `GET /tag-lists` is open to every signed-in user (active lists and tags only); managers (`taglists.manage`, institution scope) also get inactive ones and usage counts. Faculty-scoped curriculum office roles cannot manage tag lists | People need the lists to tag; ADR 015 made lists instance-wide | Easy: scope per endpoint |  Decided in 1.8, to review |
| 1.8 | Tagging needs `tagging.edit` at the item's scope (module coordinators and above; lecturers have none); published and archived versions are read-only | Same split as the structure and objectives (ADR 028, ADR 031) | Easy |  Decided in 1.8, to review |
| 1.8 | The Admin section got its first screen, `/admin/tag-lists`; the Admin menu item now also shows for `taglists.manage` | The tag list screen is an admin task and the mockup nav has no other place for it | Easy |  Decided in 1.8, to review |
| 1.8 | Reordering tags within a list is not built (new tags go to the end) | Not asked for in the slice; positions already exist | Easy: a move endpoint like ADR 029 |  Decided in 1.8, to review |
| 1.9 | Assessment fields: name, method (an `assessment_method` tag value), weight (% of the module mark, 0 to 100), timing (free text), learner time in the assessment (minutes); items have a label and marks (ADR 035) | Brief: assessment = module, name, type (tag), weight, timing; item = label, marks, linked objectives. Time is added because the brief counts assessment time in notional hours | Easy: columns |  Decided in 1.9, to review |
| 1.9 | An item may assess only objectives of its own module and of that module's sessions; programme outcomes are reached through the upward links | Keeps the scope of an item inside its module (so permissions and copying stay simple); the blueprint (phase 3) can roll up through the links | Easy: relax the check in `assessments._check_objectives` |  Decided in 1.9, to review |
| 1.9 | Changing assessments needs `curriculum.edit` at the module (module coordinators and above); lecturers read only; assessments are shown only where the whole module is visible | Same split as sessions (ADR 028); no new permission needed for a minimal slice | Easy: a dedicated permission later |  Decided in 1.9, to review |
| 1.9 | Weights are not forced to add up to 100; the module screen says in words when they do not | Brief: the checks are advice and never block saving | Easy |  Decided in 1.9, to review |
| 1.9 | Credit check figures live in `settings["credits"]`: 10 hours per credit, tolerance 10%, 120 credits per year, optional minimum credits at the exit level (off) | Brief section 9 gives the first three; the exit-level minimum is not in the brief and the HEQSF figure could not be verified, so it is off until an institution sets it. Changed through the settings API like the other sections; no settings screen yet (Slice 1.30) | Easy |  Decided in 1.9, to review |
| 1.9 | A module's tolerance edge counts as fitting (exactly 10% under or over is `ok`); a module with 0 credits is `over` once any time is planned; no credits means 'cannot compare' | The brief says 'beyond' the tolerance | Easy |  Decided in 1.9, to review |
| 1.9 | Notional hours = contact minutes + self-study minutes of the live sessions + time in the assessments | Brief section 9 | Easy |  Decided in 1.9, to review |
| 1.9 | Year check: only phases of kind `year` are compared, exactly with the typical credits per year (no tolerance); blocks, other phases and modules outside any phase are totalled only | 'Year' needs a definition; the phase kind is the one the institution already sets. Credits are whole-number rules, so no percentage tolerance | Medium if years should be derived from the programme duration |  Decided in 1.9, to review |
| 1.9 | NQF check: credits totalled per module level; findings for total different from the programme's total credits, total below the qualification type's minimum, modules above the programme's NQF exit level (the programme field, else the qualification type's) and, if set, too few credits at the exit level | The seeded qualification types hold only the exit level and minimum total credits; richer per-level rules are not in the brief. The page reminds readers to verify against CHE/HEQSF | Medium: richer rules need more qualification type fields |  Decided in 1.9, to review |
| 1.9 | The credit check page (`/curriculum/versions/:id/credits`) and the version check are for people who see the whole version (404 otherwise); a narrower role sees only the module's own check in its details | Year and NQF totals would reveal modules the person cannot see | Easy |  Decided in 1.9, to review |
| 1.9 | 'Assessment' is a fixed word, not one of the renamable terms; the demo shows its modules as 'under' on hours because it has only a few sessions each | Adding a term touches the settings enum, the translations and the terminology docs; not needed for a minimal slice. The demo is a sample, not a full curriculum | Easy |  Decided in 1.9, to review |
| 1.9 | Reordering assessments and items and an Assessments column in the tree are not built (new ones go to the end) | Not asked for in the slice | Easy: move endpoints like ADR 029 |  Decided in 1.9, to review |
| 1.10 | Pack format version 2 is opt-in with `"format_version": 2`; a pack without it is version 1 and unchanged. A version 2 section in a pack that does not say so is refused | Old packs keep working; a typo cannot silently drop a section | Easy |  Decided in 1.10, to review |
| 1.10 | A crosswalk in a pack always runs from an earlier version already imported to the pack's own version | The pack is the new side; the crosswalk model already has this direction | Medium: crosswalks between two imported versions would need their own import |  Decided in 1.10, to review |
| 1.10 | A reference to another framework or earlier version that is not imported is an error, not a skipped line | Skipping would lose links without anyone noticing; the message says to import the other framework first | Easy |  Decided in 1.10, to review |
| 1.10 | A tag list in a pack that already exists only gets the tags it lacks (by code, else label); nothing existing is changed or removed. A pack with tag lists also needs `taglists.manage` | Importing must not rewrite lists people already use; tag lists have their own permission | Easy |  Decided in 1.10, to review |
| 1.10 | The file is the raw request body (not a multipart form); a valid preview keeps it in Redis for 30 minutes under a random token tied to the user, and confirming sends only the token | No second upload of a big file; limits `PACK_MAX_UPLOAD_MB` 10 and `PACK_MAX_ITEMS` 20 000 are settings | Easy |  Decided in 1.10, to review |
| 1.10 | Imported versions are drafts unless "Make this the active version" is ticked; there is no delete or edit of a framework yet | Import must not change what is active by surprise; the library and browser come in 1.11 | Easy |  Decided in 1.10, to review |
| 1.10 | Problems are found in two stages: field-level problems first; the tree, reference, crosswalk and database checks only once those are fixed | The tree checks need a well-formed pack | Easy |  Decided in 1.10, to review |
| 1.10 | The messages about the file (problems, notes) come from the server in English; the screen text itself is translated | Same as other server messages; translating each rule is a larger change | Medium |  Decided in 1.10, to review |
| 1.10 | Templates carry `metadata.template: true` and cannot be imported until it is removed; they hold placeholders only (HPCSA: two generic areas; NQF: ten levels titled by number; graduate attributes; MeSH: two broader and two narrower placeholders) | Placeholders must not become a real framework; no official text could be verified or licensed | Easy |  Decided in 1.10, to review |
| 1.10 | Only JSON is read (the brief also mentions YAML) | Smallest step; a YAML parser is a later addition | Easy |  Decided in 1.10, to review |
| 1.10a | A tag already applied is passed on to newer items only by an explicit **Pass it on** action; an item counts as "not reached" when it lacks a direct tag and has no tagging from this tagging, so an item that already has the tag from another source is offered the second source, as in the Add tag preview | Keeps "apply once" (ADR 034) and matches the preview the person already knows | Easy | Decided in 1.10a, to review |
| 1.10a | Tag lists are institution-wide or one faculty's. `taglists.manage` at a faculty manages that faculty's lists only; faculty managers cannot create or change institution-wide lists or other faculties' lists. The brief says only "Curriculum office: tag lists, scope Faculty" | Keeps who edits which list coherent; widening it (faculty managers editing shared lists) would let one faculty change another's wording | Easy: a different check in `list_manage_scope` and `create_tag_list` | Decided in 1.10a, to review |
| 1.10a | A faculty's list is visible to people with any role in that faculty (including a programme, module or session of it) and to instance-wide roles; it can tag, and be a format or method for, only that faculty's items. The faculty of a list cannot change; keys stay unique across the institution; pack-created lists are institution-wide and need the instance permission; `frameworks.manage` stays instance-level | The brief gives no visibility rule; this keeps tagging pickers free of lists that cannot be applied | Medium (visibility rule is in `visible_faculty_ids`) | Decided in 1.10a, to review |
| 1.10a | The exit-level minimum is stored on the qualification type and used at the type's own exit level only; the institution's `min_exit_level_credits` setting overrides it. The 120-credit figures are entered as given by the product owner; the Stellenbosch source could not be fetched | The type, not the programme, carries the rule; a programme with another exit level should not be judged by it | Easy | Decided in 1.10a, to review (figures to verify) |
| 1.10a | Frameworks can be deleted (soft) only when nothing is mapped to them; accounts can be deleted by users.manage, which replaces their details and removes roles but keeps the row. Chosen instead of a separate e2e database | Smallest audited way for tests to clean up; the full POPIA deletion flow remains to be built | Easy | Decided in 1.10a, to review |
| 1.11 | Anyone with `curriculum.view` or `frameworks.manage` at any scope may read the framework library and trees (the rule the navigation already used); others get 403. Students (view published only) do not. The brief gives no rule for reading frameworks | Frameworks are institution-wide reference data, so no narrower scope exists; matches the Frameworks menu entry | Easy (one function, `may_read_frameworks`) | Decided in 1.11, to review |
| 1.11 | "Where mapped" follows ADR 027 exactly: drafts are visible to people with `curriculum.view` (not only published), programme outcomes only to people who see the whole version, module outcomes to those who see the module, session objectives to those who see the session. Anything else is left out of lists and of counts | Reuses the curriculum visibility code, so the framework screen cannot show more than the curriculum screens. The brief said "published/visible only"; this reads it as "what the user can see" | Easy | Decided in 1.11, to review |
| 1.11 | Rejected links are hidden; accepted, suggested and "waiting for a second review" links are shown, each labelled in words, with the "wording changed" and "reviewers disagree" flags. No reviewer names are shown | A rejected link is not a mapping; reports must show re-check flags (ADR 032); names of reviewers are personal data not needed here | Easy | Decided in 1.11, to review |
| 1.11 | The library lists loaded frameworks only, with their versions as a plain list. The mockup's "Needs content" and "Not loaded" template cards, coverage bars, link counts, the crosswalk and migration panel and the Excel buttons are not shown; the "template flag" is a note that points to the blank templates on the Import page. Imported frameworks are never templates (the importer refuses them) | Phase 1 plan decision 2 hides Phase 2 items; coverage is Slice 1.24 and Excel Slice 1.26; a template flag on stored frameworks would never be true | Easy | Decided in 1.11, to review |
| 1.11 | The tree is read one parent at a time, 100 siblings a window (max 200), with "Show more" and "Show earlier" rows; no virtualised list and no whole-tree download. Search is a case-insensitive substring match on code and title, no new index; meaning-based search stays in Slice 1.15 | Keeps a 20 000 item framework fast without a new dependency; a substring scan of one framework is quick enough (measured) | Medium (virtualising or a trigram index would be an addition) | Decided in 1.11, to review |
| 1.11 | The library page has a Delete button per version for `frameworks.manage`, after a confirmation, using the 1.10a endpoint; the server's 409 refusal is shown in words | The endpoint already existed and the dialog was small; the API still checks the permission | Easy | Decided in 1.11, to review |
| 1.12 | Coverage scale 0 to 5 is the Charité scale as the product owner gave it (0 none, 1 to 20%, 2 to 40%, 3 to 60%, 4 to 80%, 5 to 100%), replacing the mockup's looser anchors. The citation (Theurich et al. 2025, GMS J Med Educ 42(4):Doc46) was supplied, not fetched, so it is **not verified** | The brief gave no wording; the owner chose it | Easy (translation block) | Approved by the product owner 2026-10-27 (citation unverified) |
| 1.12 | Depth has a fourth value, Not applicable (items with no stated or implied depth: no penalty); the brief listed three. Weighted coverage will reduce a link by one point when depth is Below (Charité method); recorded in ADR 039, nothing computes it yet. Migration 0018 replaces the CHECK constraint | Keywords and topic lists have no level to compare | Medium (a data migration if the value is ever dropped) | Approved by the product owner 2026-10-27 |
| 1.12 | The "?" help text is the owner's wording, word for word, with the per-level labels and depth definitions listed beside it and the wording of the chosen level shown in the dialog | Help is visible without hovering | Easy | Approved by the product owner 2026-10-27 |
| 1.12 | `mapping.edit` at the objective's scope makes, changes and removes links; only draft versions (409 otherwise); an objective the user cannot see is 404 | ADR 012, 027, 030, 031 | Easy | Approved by the product owner 2026-10-27 |
| 1.12 | A hand-made link is accepted at once when its author holds `mapping.review` at the objective, goes to a second review in four-eyes mode, and is a suggestion when the author cannot review. **Reading of "author as first reviewer":** I record a non-reviewer author only as the creator (`created_by_id`) and leave the first reviewer empty on the suggestion, because the first review would overwrite it; a reviewer author is the first reviewer | An undecided suggestion has no reviewer | Easy | Approved in principle 2026-10-27; the first-reviewer detail needs a look |
| 1.12 | Editing a link is a new claim and is decided again: a reviewer's edit keeps it accepted, or sends it to a second review in four-eyes mode (also when it was accepted); an edit by anyone else returns it to suggested; an edit that changes nothing changes nothing | The earlier acceptance was of different values | Easy | Approved by the product owner 2026-10-27 |
| 1.12 | `needs_recheck` is cleared only by "Still fits" (`mapping.review`, the existing `confirm_recheck`), never by an edit | ADR 032 | Easy | Approved by the product owner 2026-10-27 |
| 1.12 | Adding a link for a pair with a rejected row reopens that row as a human link (AI confidence and quote cleared). Removing a hand-made or imported link deletes it; removing an AI or migrated link rejects it (reviewer only) so it stays as an example | One row per pair (ADR 016); rejected rows are examples | Easy | Reopening approved 2026-10-27; the removal rule is mine and needs a look |
| 1.12 | The workspace is a button-and-dialog flow (select objective, select item, Link): no drag and drop. Links of a soft-deleted objective still count as mapped and stop their framework being deleted (existing 1.10a rule) | Keyboard and single-pointer access; the mockup's drag was not required | Easy | Decided in 1.12, to review |
| 1.13 | A **first review** needs `mapping.review` and a **second review** needs `mapping.second_review`, both at the objective's scope (the permission already in the catalogue; mapper, programme director, curriculum office and platform admin hold it, the module coordinator does not). The review endpoint checks the permission of the link's stage; a link the user cannot see is 404 | The brief gives the mapper "first and second review" and coordinators "review AI suggestions"; a separate permission is what makes a second pair of eyes meaningful. **Consequence to look at:** a module coordinator cannot give second reviews in four-eyes mode | Easy: one choice of permission in `mapping_review.review` and `load_queue` | Decided in 1.13, to review |
| 1.13 | Four-eyes in the service: the second reviewer must differ from the first reviewer (as before) **and the author of a hand-made link cannot give its second review either**, also when someone else gave the first (new in `mapping.review_link`). The queue leaves out and does not count links the user may not second | ADR 016 says hand-made links count as reviewed by their author; 1.12 left a non-reviewer author without a named reviewer, so this closes the gap where the author could later second a colleague's first review of their own suggestion | Easy: one condition | Decided in 1.13, to review |
| 1.13 | The queue has three piles: first review (`suggested`), second review (`needs_second_review`) and **re-check** (accepted with `needs_recheck`, decided with the existing "Still fits"). The sidebar count is the **total of the three**. Only draft versions the user can see are listed; a link in a published version is 409. Rejected links are hidden | "needs_recheck must show": a flagged accepted link is work for a reviewer; published versions are read only (ADR 030) | Easy: counts and tabs derive from one list | Decided in 1.13, to review |
| 1.13 | A decision carries the `expected_status` the person saw; a link that moved on is a 409 and nothing is saved | Without it, two people working at once could turn a first review into a second review by accident (the service picks the stage from the status) | Easy | Decided in 1.13, to review |
| 1.13 | **Bulk accept** ("Accept all N and above"): threshold at least 80% (offered 80, 85, 90, 95; default 90); only first-pile suggestions with a confidence, a coverage and a depth, so never a link a person suggested, never a second review or re-check; never the user's own; within the filters on the screen; at most 200 per action, most confident first; in four-eyes mode it is only a **first review**; the screen counts first (dry run) and states the rules; one audit operation `mapping.review_bulk_accept` | The brief says "bulk accept above a chosen confidence"; the mockup calls under 65% "check carefully". The floor, the batch cap and "never second reviews" are my safety choices | Easy: two constants and one filter | Decided in 1.13, to review (floor and cap are the numbers to confirm) |
| 1.13 | Progress "N of M suggestions reviewed" counts the links of the chosen scope that the AI or a migration made, plus any link waiting for a person; hand-made links accepted at once are not suggestions. Reviewed = accepted + rejected + second review | A person's own accepted link was never a suggestion | Easy | Decided in 1.13, to review |
| 1.13 | **Keyboard shortcuts** (A, R, E, S, 2) work only while focus is inside the list or the details, never in a text field or with Ctrl, Alt or Meta, and a **switch turns them off** (kept in this browser; default on). E moves focus to the coverage choice; A then accepts with the chosen values. "2" also works without four-eyes mode (the first reviewer is unsure). Skip only moves on | WCAG 2.1.4 allows single-key shortcuts that are off-able or active only on focus; both are done. Screen readers that capture letters in browse mode do not pass them on, so every action is a button too | Easy | Decided in 1.13, to review |
| 1.13 | Edit means the **coverage and depth** (as in the mockup), not the reason: the reason stays the author's or the AI's words. Accepting needs both values (422 otherwise). A reviewer's accept with changed values is audited as `..._accept_edited` | Matches the mockup's pickers; the wording of a reason is the author's | Easy | Decided in 1.13, to review |
| 1.13 | For suggestions by a person the AI-only parts render sensibly: "Why this link was suggested", no confidence bar ("Suggested by a person, no confidence score"), highlighted evidence only when a quote exists. Left out of the mockup: "also mapped from N other objectives" (it would count objectives the user may not see), the run label (no AI runs yet) and the version button in the header (the filters hold it) | Phase 1 plan decision 2 and ADR 027 | Easy | Decided in 1.13, to review |
| 1.13 | Rejecting in the queue and removing an AI or migrated link in the workspace (1.12) both end as `rejected`, kept as an example. Nothing in the screens reopens a rejected link yet (`mapping.reopen` exists in the service) | Consistent with ADR 016; a "rejected" list and reopening were not asked for | Easy: a stage and an endpoint | Decided in 1.13, to review |
| 1.13 | The queue loads the small candidate rows of the user's draft versions and filters them by scope permissions in memory (as the workspace does), then loads the cards of one page | Simple and correct; tens of thousands of waiting suggestions would want a SQL filter | Medium | Decided in 1.13, to review |
| 1.14 | **AI is off and local-only mode is on by default**; choosing a cloud provider is two deliberate steps (turn local-only off, tick the acknowledgement). Turning AI off withdraws the acknowledgement | The brief: everything must work without AI; "most restrictive default" | Easy: column defaults | Decided in 1.14, to review |
| 1.14 | **Budget defaults are caps, not allowances**: monthly cost USD 10.00, 2 000 000 tokens, 2 000 calls, 500 calls per run, 1 024 tokens per answer; an empty field means no limit | The brief wants "stop at budget caps with a clear message"; no default spends money until a provider is chosen, and then it is limited. The numbers are a guess for the owner to set | Easy: column defaults and the screen | Decided in 1.14, to review |
| 1.14 | **No prices are built in.** The admin enters USD per million input and output tokens; with a cost limit set, a non-local provider without prices is refused ("enter prices, or 0 for a server you run") | Prices change and could not be verified against a source for every provider (only model ids were read from Anthropic's page). Blocking on missing prices is the safe side of "cost cannot be counted" | Easy | Decided in 1.14, to review |
| 1.14 | **The admin states where a provider processes text** (local, South Africa, outside South Africa); Anthropic is fixed at outside; OpenAI-compatible defaults to outside; Ollama to local; "local" is only accepted for private addresses. The code never guesses a region from a name | Which regions count as "outside SA" is a legal question; "unknown" is treated as outside, the warning side | Easy | Decided in 1.14, to review |
| 1.14 | **Personal data: refuse by default, redaction is an admin choice.** What counts: emails, phone numbers, SA ID numbers, student/staff/ID numbers and any 7 to 12 digit run, IPv4 addresses, a title (Dr, Prof, Mr ...) plus a name, and the display names of this installation's users (whole name; single-word names of 4+ letters). Names of non-users are found only with a title | The brief says never send and also lists redaction; refusing is the strict reading. False alarms refuse a call, which is the safe direction. The English/South African patterns are a first set; the owner may want more (other languages, patient identifiers) | Medium: new rules are small, but each needs tests | Decided in 1.14, to review |
| 1.14 | **Encryption key**: Fernet from `cryptography`; keys in `SECRETS_ENCRYPTION_KEYS` (newest first) plus a key derived from `SECRET_KEY` always kept for reading; `rotate-secrets` re-encrypts (ADR 041). No last-four hint is shown, only "set" | Works with no extra setup, and a dedicated key is the recommended way; a hint needs the plaintext | Medium: stored values carry a key id | Decided in 1.14, to review |
| 1.14 | The Phase 0 environment variables `AI_ENABLED`, `AI_ANTHROPIC_API_KEY`, `AI_OPENAI_API_KEY`, `AI_OPENAI_BASE_URL`, `AI_OLLAMA_BASE_URL`, `AI_MONTHLY_BUDGET_CAP` were removed; everything is on the admin screen | They were never read; a key in `.env` would have been a second, unencrypted place for it | Easy | Decided in 1.14, to review |
| 1.14 | **OpenAI-compatible adapter is only partly verified**: OpenAI's own API reference returned 403/404, so it is built from Microsoft's Azure OpenAI v1 reference and Ollama's compatibility page. The screen, the admin guide and ADR 042 say so and advise running the connection test | CLAUDE.md: verify against current documentation or say so | Easy to re-check later against OpenAI's page | Open: re-read when the page is reachable |
| 1.14 | **The e2e journey never presses "Test connection"** because every press writes an AI run that can never be deleted (ADR 016) | Keeps ADR 037's "leave nothing behind"; the button is covered by API tests with a mocked provider | Easy | Decided in 1.14, to review |
| 1.14 | Refusals reach the API as 409 (`AIRefusedError`) and provider failures as 502 (`ProviderError`); the test button answers 200 with `ok: false` and a reason code | Later features need a stable way to show "AI is off / over budget / personal data found" | Easy | Decided in 1.14, to review |

---

## Phase 1 Plan (approved 2026-10-25)

Product name: **Curriculum in Context** (repository, Python package, CLI, images and compose project stay `ocmp`). UI reference: the approved mockups in `docs/mockups/` (start with its README).

### Decisions

| # | Topic | Decision |
|---|---|---|
| 1 | Contrast | Light `--faint` darkened to about `#5F6B76` (was 4.26:1 on `--bg`); new `--field-line` token at 3:1 or more for inputs and toggles in both themes; card borders stay as designed; token table in `docs/mockups/README.md` updated to match |
| 2 | Phase 2 items in the mockups | Hidden in Phase 1, no placeholders: declared vs delivered, Brightspace card, evidence pack button, framework version/crosswalk panel, session times and venues. The dashboard is rearranged so nothing looks missing; the student "This week" lists sessions by week number |
| 3 | AI tasks from brief section 8 | Study-guide extraction (PDF/DOCX to draft objectives) is a Phase 1 slice. "Explain this gap", "Suggest sessions" and Q&A are deferred to Phase 2; their buttons stay hidden |
| 4 | Demo data | Keep the 3-module demo; add a published 2026 version and a 2027 draft made by copy-forward (Slice 1.5), seeded metrics history (1.28) and the AI gold set (1.19) |
| 5 | Charts | Plain SVG components instead of ECharts (ADR); Cytoscape stays for the Phase 2 network view |
| 6 | Rename scope | "Curriculum in Context" in UI, docs site, README, emails, OpenAPI title and page titles; no acronym |
| 7 | Navigation | As the mockup sidebar: Dashboard, Curriculum, Mapping, Review queue (sub-item), Frameworks, Reports, Import and export, Search, Admin. Students: Explorer and Search |
| 8 | Public API | Personal API tokens in Phase 1 (Slice 1.30); webhooks in Phase 2 |
| 9 | Fonts | IBM Plex Sans and Mono self-hosted (OFL), no third-party requests |
| 10 | Embeddings | Model and server proposed as an ADR at the start of Slice 1.15 |

### Slices

| # | Slice |
|---|---|
| 1.0 | Dependency upgrades: Node current LTS, Mantine 7 to 9, react-i18next 15 to 17, eslint-plugin-react-refresh 0.5, GitHub Actions majors (React 19 if Mantine 9 needs it) |
| 1.1 | Product name ADR and rename; design tokens (CSS variables, light/dark) mapped into the Mantine theme; self-hosted IBM Plex; theme toggle; shared layout (sidebar, wordmark, icon nav, review count slot, header); shared empty/loading/error components; Playwright with axe checks in both themes |
| 1.2 | Curriculum read API; programme/version switcher; read-only builder structure tree with states |
| 1.3 | Structure editing: phases, modules and learning events CRUD with scoped permissions |
| 1.4 | Reorder (drag and drop with keyboard alternative) and copy items with children |
| 1.5 | Curriculum versions: publish rules, copy academic year forward, version diff; demo gets 2026 published and 2027 draft |
| 1.6 | Objective editor at each level: upward links, domain, taxonomy level |
| 1.7 | Rule-based objective quality checker (live and bulk) and taxonomy level suggestion from verb lists |
| 1.8 | Tag lists managed by the curriculum office; tagging with inheritance preview and source |
| 1.9 | Minimal assessments (items linked to objectives); credits and notional hours check per module, year and NQF level |
| 1.10 | Framework pack import from the UI (schema extended for crosswalks, tag lists, cross-references); structure-only templates (HPCSA, NQF, graduate attributes, MeSH subset) |
| 1.10a | Review changes to 1.7-1.10: pass a tag on to newer items, faculty-scoped tag lists, exit-level minimum credits in the qualification types, end-to-end cleanup (framework and account delete) |
| 1.10b | Demo: faculty-scoped curriculum-office account and a faculty tag list |
| 1.11 | Framework library screen and tree browser with search and "where mapped" |
| 1.12 | Mapping workspace: manual linking, coverage 0-5 (Charité scale) and depth (below, matches, above, not applicable) with help text; ADR 039 |
| 1.13 | Review queue: API and screen, keyboard shortcuts, bulk accept, four-eyes, sidebar count |
| 1.14 | AI provider layer (Null, Anthropic, OpenAI-compatible, Ollama), privacy guard and redaction, encrypted keys, budgets, local-only, outside-SA warning, admin AI settings screen |
| 1.15 | Embeddings image and text-hash cache in pgvector; near-duplicate detection in the checker (ADR first) |
| 1.16 | AI mapping pipeline: hybrid shortlist, versioned prompt, validated JSON, job progress and error states, few-shot from decisions |
| 1.17 | AI objective rewrite (diff to accept) and domain/level classification |
| 1.18 | Study-guide extraction: PDF/DOCX upload to draft objectives for review |
| 1.19 | Evaluation harness (script and admin page) with fictional gold set: precision, recall, Cohen's kappa |
| 1.20 | Search: full-text and meaning-based with filters; "Where do we teach X?"; header search |
| 1.21 | Coverage engine (four labelled methods), coverage report with heatmap, gap report |
| 1.22 | Report exports to Excel and PDF, each stating method and date |
| 1.23 | Redundancy and traceability reports |
| 1.24 | Teaching formats and contact hours, curriculum relationship, role balance (health profile), assessment methods coverage |
| 1.25 | Excel templates from field definitions; import engine with preview, dry run, row errors, upsert by external ID (structure and objectives) |
| 1.26 | Excel imports for tags, frameworks and mappings; import job history |
| 1.27 | Exports: full round trip, objectives x framework items matrix, JSON of a version |
| 1.28 | Committee dashboard: KPI trends from nightly metric snapshots (seeded for the demo), traceability diagram, coverage vs last published version, mapping progress, credit table |
| 1.29 | Student and staff explorer (phone first): published versions only, search, "what is covered in this module/assessment" |
| 1.30 | Admin screens (users, roles, assignments, institution settings); personal API tokens; `remove-demo` command |
| 1.31 | End-to-end journeys complete; user guides per role, glossary, FAQ, AI provider setup guide; Phase 1 definition-of-done review |

Each slice: its screen states, tests, docs, PROGRESS.md entry and one Conventional Commit; Playwright journeys are added as screens arrive.

---

### Slice 1.0: Dependency Upgrades
**Status**: Complete

**Deliverables**:
- [x] **Node.js 24** (current LTS, "Krypton", checked against the Node.js release schedule on 2026-10-25) in CI, the web image (`node:24-alpine`) and CONTRIBUTING; `@types/node` 24. Node 26 becomes LTS on 2026-10-28, three days after this slice; the owner chose to stay on 24 and move to 26 early in Phase 2
- [x] **Mantine 7 to 9.7.3** (core, hooks, form, notifications). Mantine 9 requires **React 19.2**, so React and React DOM moved to 19 (`@types/react` 19). No code changes needed: none of the removed props or hooks were used, and the theme already sets its radius
- [x] **react-i18next 15 to 17**, which requires **i18next 26** (from 23); none of the removed init options were used
- [x] **eslint-plugin-react-refresh 0.4 to 0.5**, which requires **ESLint 9**: `.eslintrc.cjs` replaced by flat config `eslint.config.js` (same rule sets; `reactRefresh.configs.vite()` keeps constant exports allowed); `typescript-eslint` package replaces the separate parser and plugin; `eslint-plugin-react-hooks` 4 to 7. ESLint stays on 9 because `eslint-plugin-react` does not support 10 yet
- [x] The new React Hooks rule `set-state-in-effect` flagged the sign-in "taking longer" note; the reset moved into the effect cleanup, with a new test for the note appearing and disappearing
- [x] **Also upgraded (not in the Dependabot list)**: all 9 `npm audit` findings (3 critical, 1 high) were already present and came from Vite 5, Vitest 2 and React Router 6; Dependabot had stopped at its limit of 5 open npm pull requests. Upgraded to **Vite 8** (Rolldown: `manualChunks` replaced by `codeSplitting` groups), **@vitejs/plugin-react 6**, **Vitest 5**, **jsdom 30**, **@testing-library/jest-dom 7** (now imported from `@testing-library/jest-dom/vitest`) and **React Router 7** (imports moved from `react-router-dom` to `react-router`). `npm audit`: 0 vulnerabilities. Lockfile regenerated
- [x] TypeScript stays on 5.9: TypeScript 6/7 exist but `typescript-eslint` supports below 6.1 only
- [x] **GitHub Actions majors**: `actions/checkout` 7, `actions/setup-python` 7, `actions/setup-node` 7, `codecov/codecov-action` 7.1.1, `docker/setup-buildx-action` 4.4.1, `docker/build-push-action` 7.4.0 (third-party pinned to commit SHAs); release notes checked: the breaking changes are the Node 24 action runtime and inputs this repository does not use
- [x] ADR 002 revised (Mantine 9, React 19); CLAUDE.md stack line updated

**Verification**:
- Frontend under Node 24.22.1: lint, typecheck, production build pass; 56 tests pass (90.5% line coverage); no warnings in the test run; library chunks split as before (app code 10.9 kB gzipped)
- Backend: ruff, ruff format, mypy (69 files) pass; pytest 515 passed against the test database, 96% coverage; `mkdocs build --strict` passes
- Docker: web image builds on `node:24-alpine`; stack healthy, `/ready` ready
- Real browser (temporary Playwright Chromium against the Docker stack): sign-in page renders, wrong credentials show the error, forgotten-password page sends its confirmation, dark colour scheme applies; no console errors besides the expected 401s
- Not verified here: the workflows themselves on GitHub Actions (runs on push)

**Commit**: `chore: upgrade to Node 24, React 19, Mantine 9, ESLint 9, Vite 8 and current actions`

---

### Slice 1.1: Name, Design Tokens, Shared Layout and Accessibility Checks
**Status**: Complete

**Deliverables**:
- [x] **Product name "Curriculum in Context"** (ADR 025): UI (two-tone wordmark in the sidebar and on the sign-in pages, page title, favicon), docs site, README, CONTRIBUTING, SECURITY, operator and admin guides, email sender name and subjects (`APP_NAME`, `SMTP_FROM_NAME` defaults), OpenAPI title, setup message, demo data ("Demo University") and pack schema title. Technical identifiers stay `ocmp`; ADRs 001-024 unchanged as records. Renamed headings changed two doc anchors; links updated
- [x] **Design tokens** (ADR 026): `src/theme/tokens.ts` is the single source; the CSS variables resolver writes `--cic-*` per scheme; Mantine's semantic variables, `gray`/`dark` palettes, primary `brand` colour and red variants point at the tokens; filled brand buttons use on-brand text; `global.css` sets 44px buttons and fields, card surfaces, menu colours. Phase 1 decision 1 applied: light `faint` `#5F6B76`, new `fieldLine` (`#7F8A93` / `#667A7D`); token table in `docs/mockups/README.md` updated (plus `ok`/`ok-soft` from the dashboard mockup)
- [x] **Self-hosted IBM Plex** Sans and Mono via `@fontsource` (OFL), bundled by Vite; no third-party requests (checked in an end-to-end test)
- [x] **Theme toggle**: follows the system until chosen, remembered in local storage; `public/color-scheme.js` applies the saved scheme before the app loads (no light flash; external file so a future CSP can allow it); the toggle's label names the theme it switches to
- [x] **Shared layout**: dark teal sidebar from the mockup (wordmark, icon navigation, Review queue as a sub-item under Mapping with a count slot whose number has a text label, "Import and export" item, institution name), header with theme toggle and an initials avatar menu. Navigation order per Phase 1 decision 7; most specific item is the current page (`activeNavKey`). On phones the header stays above the open navigation and the closed navigation is hidden from keyboard and screen readers; the menu button has `aria-expanded`
- [x] **Shared components** in `src/ui/`: `Page` (padding, the only `h1`) and `EmptyState`, `LoadingState` (progress bar or status, skeletons, `aria-busy`), `ErrorState` (`role="alert"`, hint box) from the States mockup. Status pages, account page and the session error page use them; the sign-in card shows the wordmark
- [x] **Playwright with axe** (`frontend/e2e/`, ADR 006 and 026): light and dark projects; WCAG 2.0-2.2 A/AA checks on sign-in, forgotten password, failed sign-in, dashboard, review queue, account, not found and the open account menu; layout journeys (start page and navigation, current item, theme toggle remembered, self-hosted font, skip link, phone navigation). One sign-in per run (sign-in is rate-limited), reused locally while valid. New CI job "End-to-End Tests" starts the Compose stack, loads the demo data, creates an admin with a random password and runs the suite; `build` now waits for it
- [x] axe found and the slice fixed: initials avatar's name did not contain its visible text; Mantine Menu's focus placeholder broke the `menu` role (`withInitialFocusPlaceholder={false}`); the menu's dark hover colour was the field border colour (too dark for text); Mantine's navbar `<nav>` wrapped the labelled navigation (now `role="none"`)
- [x] `npm run typecheck` also checks the Playwright config and tests; Vitest runs only `src/**/*.test.*`; `docs/mockups/` (design-tool source) committed and excluded from the docs site
- [x] CLAUDE.md, CONTRIBUTING, ADR 006 and 019 updated; ADR 025 and 026 added

**Verification**:
- Frontend under Node 24.22.1: lint, typecheck, production build pass; 90 tests pass (90.8% line coverage), including token contrast tests (every text token 4.5:1 and field borders 3:1 on `bg`, `surface`, `soft` in both themes; sidebar colours)
- Backend: ruff, ruff format, mypy (69 files) pass; pytest 515 passed against the test database, 96% coverage; `mkdocs build --strict` passes
- Docker: web image rebuilt; Playwright 1.64.1 (Chromium) against the local Compose stack: 27 passed, twice in a row; screenshots of light and dark, the account menu and the phone navigation compared with the mockups by eye
- GitHub Actions: CI green on `acd15bb` with all seven jobs, including the new End-to-End Tests job (27 Playwright tests passed against the Compose stack on the runner); CodeQL green
- Not verified here: browsers other than Chromium; screen readers by hand
- Local note: the shell's default Node is 22.11, which cannot run Vitest 5 (`require()` of an ES module); the checks above used Node 24.22.1

**Docs workflow**: it failed on every push because GitHub Pages is not enabled yet. The Pages steps and the deploy job now run only when the repository variable `PAGES_ENABLED` is `true`; the site still builds with `--strict` on every docs push (release checklist step 3 updated). Commit `ci: skip the GitHub Pages deploy until Pages is enabled`.

**Not in this slice**: programme/version switcher in the header (Slice 1.2), header search (1.20), the review count source (1.13); a Content-Security-Policy header (not set by Caddy today) is worth adding with a later security slice.

**Commit**: `feat: rename to Curriculum in Context with design tokens, shared layout and axe checks`

**CI follow-up**: the first run of the new End-to-End job failed before any test ran. On the GitHub runner's Docker Compose, `docker compose up --wait` fails with "container ocmp-worker-1 has no healthcheck configured", because the worker had `healthcheck: disable: true` (local Compose v5.6.1 accepted it). The install, upgrade and restore guides use the same command, so installations on that Compose version would have failed too. The worker now has a real healthcheck: the Dramatiq process runs and Redis answers. Fixed in `fix: give the worker a healthcheck so compose up --wait succeeds`.

---

### Slice 1.2: Curriculum Read API, Version Switcher and Structure Tree
**Status**: Complete

**Deliverables**:
- [x] **Curriculum read API** (ADR 027), signed-in users only, each answer filtered to what the user may see: `GET /programmes` (with visible versions, newest first), `/programmes/{id}` (qualification, NQF, credits, SAQA ID, accreditation), `/curriculum-versions/{id}/structure` (phases, modules, sessions in order with formats and objective counts; longitudinal modules separately; `partial` flag), `/curriculum-versions/{id}/outcomes`, `/modules/{id}` (totals of contact and self-study time, outcomes with upward links), `/learning-events/{id}` (objectives with upward links). Not visible = 404
- [x] **Who sees what** (`app/services/curriculum_read.py`): permissions gathered once per request from the user's role assignments. Programme level and above: whole version; module role: that module and its sessions; session role: that session, under its module as context only. `curriculum.view_published` shows published versions only. Deleted rows and programmes of deleted faculties are hidden. `role_permissions` in the authorization service made public so both paths expand implied permissions the same way
- [x] **Programme and version switcher**: a menu in the header (in the page on phones) grouped by programme, the open version marked with `aria-current`; the last opened version is remembered in this browser and `/curriculum` opens it while it is still visible, otherwise the newest version of the first programme
- [x] **Read-only builder** (`/curriculum/versions/{id}?item=...`): structure tree (own ARIA tree: roving tab stop, arrow keys, Home/End, Enter/Space; flat with `aria-level`/`aria-posinset`/`aria-setsize`; root and phases open by default, the way to an item named in the address opened) and a details panel per item: programme facts and programme outcomes, phase and "Across phases" totals, module facts and outcomes, session facts and objectives (domain, status, upward-link chips as in the mockup). Curriculum nouns come from `terms.*`, so institution terminology applies
- [x] **States**: loading (skeletons), load error with retry, unknown or hidden version (explains and links to the latest version), no programmes (admins get the `load-demo` hint), version without modules, narrower roles told they see only their modules and sessions
- [x] Test setup: Testing Library waits up to 3 s for `findBy*`/`waitFor` (the first full-app render in a busy parallel run sometimes took over 1 s and failed an existing route test once)
- [x] ADR 027; admin guide "Who sees which curriculum"; CLAUDE.md (folder and service)

**Verification**:
- Backend: ruff, ruff format, mypy (72 files) pass; pytest 543 passed against the test database (28 new API tests: sign-in required, full, faculty, instance, published-only, module-scope, session-scope and no-role users, ordering, deleted rows, qualification type), 96% coverage (`curriculum_read.py` 96%)
- Frontend under Node 24.22.1: lint, typecheck, production build pass; 110 tests pass, twice in a row (20 new: tree model, version choice, page states, keyboard navigation, deep links, switcher, terminology), 92% line coverage
- Docker: api, worker and web images rebuilt; Playwright (Chromium) against the Compose stack with the demo data: 37 passed, twice in a row (10 new in `e2e/curriculum.spec.ts`: structure and programme details, keyboard to a session and reload, open switcher menu, unknown version, phone layout; axe WCAG 2.2 AA on each, light and dark)
- Screenshots of light, dark (session selected) and phone compared with `Builder.dc.html` by eye; chips and lowercase counts adjusted to match
- `mkdocs build --strict` passes
- Not verified here: browsers other than Chromium; screen readers by hand; the CI run on GitHub (runs on push)

**Not in this slice**: editing (1.3), objective quality flags and tags in the details panel (1.7, 1.8), the module credit check (1.9), "Publish version" and copy forward (1.5).

**Owner decisions (2026-10-25)**:
1. People with only a module or session role keep seeing the programme's name and details, read-only (as built)
2. For Slice 1.5: copying a year forward **copies role assignments at module and session scope** to the new rows by default. The copy-forward preview lists them so each can be unticked; assignments that have expired, or whose account is deactivated or deleted, are skipped (and shown as skipped)

**Commit**: `feat: add curriculum read API, version switcher and read-only structure tree`

---

### Slice 1.3: Structure Editing
**Status**: Complete

**Deliverables**:
- [x] **Editing API** (ADR 028): `POST /curriculum-versions/{id}/phases`, `PATCH`/`DELETE /phases/{id}`, `POST /curriculum-versions/{id}/modules`, `PATCH`/`DELETE /modules/{id}`, `POST /modules/{id}/learning-events`, `PATCH`/`DELETE /learning-events/{id}`, and `GET /teaching-formats` (values of active teaching-method lists). Partial updates (`PATCH` changes only the fields sent; `null` clears optional ones); validation of names, codes, credits (one decimal), NQF level, minutes and week
- [x] **Scoped permissions**: `curriculum.edit` at the programme for phases, adding and deleting modules and moving a module between phases; at the module for its fields and adding or deleting its sessions; at the session for its fields. Not visible = 404 (ADR 027), visible but not allowed = 403. `require_permission` takes async scope resolvers `(request, db, user)`
- [x] **Rules** (`app/services/curriculum_edit.py`): archived versions read-only (409); phase must be in the same version; module codes unique per version ignoring case (409); new items at the end; format from a usable teaching-method list; soft delete with children (module: sessions and all their objectives; session: its objectives; one timestamp), phase only when empty (409). Every change through ORM objects with `audit_operation` names (`curriculum.phase_create` and so on)
- [x] Structure response carries `can_edit` for the version, each module and each session; `format_value_id` added to sessions
- [x] **Builder screens**: Add, Edit and Delete buttons for the selected item in the details panel, following the `can_edit` flags; Mantine modal forms for phases (name, kind), modules (code, name, phase or "across phases", credits, NQF level, description, LMS reference) and sessions (title, format, contact and self-study minutes, week, description, LMS reference); delete dialogs say what goes with the item; a phase holding modules explains why it cannot be deleted. After a change the new item (or the deleted item's parent) is selected and opened, and a `SuccessNotice` confirms it (focused when the selection moved; otherwise focus returns to the button). Editors see the builder, not the empty state, for a version without modules. All text from `curriculum.edit.*` and `terms.*`
- [x] Fixed while testing: the request's database session committed after the response was sent, so the builder's refetch after a save could miss the change (now committed before the response); filled red buttons had white text on the dark theme's light red (now on-brand text, contrast test added); the test factory's academic years overflowed the allowed range in long runs
- [x] ADR 028; admin guide "Who can change the curriculum structure"; CLAUDE.md (service and scope resolvers); "Decisions to review" section started in this file

**Verification**:
- Backend: ruff, ruff format, mypy (74 files) pass; pytest 594 passed against the test database (51 new in `test_curriculum_edit_api.py`: sign-in required, programme director, module coordinator, lecturer, mapper and student, archived and published versions, validation, cascade, audit entry), 97% coverage
- Frontend under Node 24.22.1: lint, typecheck, production build pass; 119 tests pass (9 new in `StructureEditing.test.tsx`: no buttons without rights, add phase with validation, edit module and phase, duplicate code, module coordinator limits, add session with format, delete session, non-empty phase, empty editable version)
- Docker: api, worker and web images rebuilt; Playwright (Chromium) against the Compose stack with the demo data: 41 passed, twice in a row (4 new in `e2e/curriculum-editing.spec.ts`: add, change and delete a phase, module and session with cancel and focus checks, and the non-empty phase; axe WCAG 2.2 AA on each dialog and state, light and dark)
- Screenshots of the module edit dialog (dark) and the module view with its buttons (light) checked by eye
- `mkdocs build --strict` passes
- Not verified here: browsers other than Chromium; screen readers by hand; the CI run on GitHub (runs on push)

**Not in this slice**: reordering and copying (1.4), publishing rules and making published versions read-only (1.5), a restore screen for deleted items, objective editing (1.6).

**Commit**: `feat: edit phases, modules and sessions with scoped permissions`

---

### Slice 1.4: Reorder and Copy
**Status**: Complete

**Deliverables**:
- [x] **Reorder API** (ADR 029): `POST /phases/{id}/move`, `/modules/{id}/move`, `/learning-events/{id}/move` with `{"position": n}` (new index among siblings: the version's phases, the modules of one phase or across phases, the sessions of one module); siblings renumbered through ORM objects, only changed rows written; audit labels `curriculum.*_move`
- [x] **Copy API**: `POST /phases/{id}/copy` (name and a new code per module), `/modules/{id}/copy` (code, name, optional phase), `/learning-events/{id}/copy` (title), 201 with the new item. New service `app/services/curriculum_copy.py`: the copy goes right after the original (or to the end of another phase); children, objectives, upward links (remapped to copies), direct and inherited taggings (inherited ones remapped) are copied; mappings, role assignments, LMS references and deleted rows are not; codes checked unique ignoring case (409); audit labels `curriculum.*_copy` with the source id
- [x] **Permissions** as ADR 028: phases and modules at the programme, sessions at the module; 404 for what the user cannot see, 403 for visible items they may not change; archived versions 409
- [x] **Builder**: Move up, Move down and Copy buttons for the selected item (Delete stays last; move buttons hidden when an item has no siblings); after a move the confirmation is announced and focus stays on the pressed button, or moves to the confirmation when that button becomes unavailable; a failed move shows an alert. Native drag and drop in the tree among siblings only (grip icon, drop line, the selection stays); a hint under the tree title says how to change the order. Copy dialog says what is and is not copied, suggests "<name> (copy)", asks for new module code(s) (checked for blanks and repeats before sending) and selects the copy. Text from `curriculum.reorder.*`, `curriculum.copy.*` and `terms.*`
- [x] ADR 029; admin guide "Who can change the curriculum structure" (reordering, copying, audit labels); CLAUDE.md

**Verification**:
- Backend: ruff, ruff format, mypy (75 files) pass; pytest 620 passed against the test database (26 new in `test_curriculum_reorder_copy_api.py`: sign-in required, moving phases, modules in a phase and across phases, sessions, position range, archived version, copying a session, a module (same phase, another phase, across phases) and a phase with links, inherited tags, mappings left out, deleted rows left out, code checks; module coordinator and lecturer limits; audit labels), 97% coverage
- Frontend under Node 24.22.1: lint, typecheck pass; 128 tests pass (9 new in `Rearranging.test.tsx`: Move up with focus to the confirmation, focus kept on a usable button, failed move, drag and drop among siblings only, no controls without rights or without siblings, module coordinator limits, copy session, copy module with code checks and phase choice, copy phase with a code per module)
- Docker: api, worker and web images rebuilt; Playwright (Chromium) against the Compose stack with the demo data: 45 passed, twice in a row (4 new in `e2e/curriculum-reorder.spec.ts`: move a module with Enter and Space on Move up / Move down and by dragging; copy a module (required and taken code), a session and a phase; axe WCAG 2.2 AA on each dialog and state, light and dark). Each journey makes its own phase and modules through the API and deletes them afterwards; the demo structure was checked unchanged after the runs
- Screenshots of the module view with its new buttons and drag grips (light) and the copy dialog (dark) checked by eye; move buttons then hidden for items without siblings
- `mkdocs build --strict` passes
- Not verified here: browsers other than Chromium; touch drag and drop on a real phone or tablet; screen readers by hand; the CI run on GitHub (runs on push)

**Not in this slice**: moving a session to another module, copying to another version (copy forward is Slice 1.5), a live preview while dragging.

**Commit**: `feat: reorder and copy phases, modules and sessions`

---

### Slice 1.5: Curriculum Versions
**Status**: Complete

**Deliverables**:
- [x] **Publish rules** (ADR 030, `app/services/curriculum_versions.py`): `POST /curriculum-versions/{id}/status` (publish, return to draft, archive, publish again; needs `curriculum.publish`; a draft needs a module); only drafts are editable (`EDITABLE_STATUSES`), so published and archived versions are read-only (409); `DELETE /curriculum-versions/{id}` for drafts. Audit labels `curriculum.version_publish`, `_unpublish`, `_archive`, `_unarchive`, `_copy_forward`, `_delete`. Structure response gained `can_change_status` and `can_copy_forward`
- [x] **Copy forward**: `GET`/`POST /curriculum-versions/{id}/copy-forward` (preview with counts, suggested year, years in use, role assignments; the copy is a new draft with phases, modules, sessions, objectives of every level, upward links, tags and framework mappings with their review state; LMS references are not copied). Reuses the ADR 029 copy machinery (`Copies` with a target version). **Role assignments** at module and session scope are copied as the owner decided: ticked by default in the preview, each can be unticked; ended assignments, deactivated or deleted accounts and roles the caller may not grant are listed as not copied with the reason
- [x] **Lineage**: migration `0013` adds nullable `based_on_id` to phases, modules, learning events and objectives (additive, indexed, `ON DELETE SET NULL`, downgrade drops them)
- [x] **Version diff**: `GET /curriculum-versions/{id}/diff?base=` (`app/services/curriculum_diff.py`): lineage first, then phase name, module code, session title and objective text; added, removed and changed items with field before and after
- [x] **Builder**: version bar with status text and Publish / Return to draft / Archive / Publish again / Copy forward / Compare versions / Delete draft (from the structure flags), confirm dialogs, copy-forward dialog with counts and role ticks, notices carried to the next page; compare page (`/curriculum/versions/:id/compare?base=`) with summary, per-kind lists and a "Compare with" choice. All text from `curriculum.versions.*` and `curriculum.compare.*`
- [x] **Demo**: published current-year version plus a next-year draft made by copy forward with scripted changes (renamed, longer, added, removed session, reworded objective); `load-demo` on an install with only the published version adds the draft
- [x] ADR 030; admin guide section "Publishing and copying a year forward"; install guide demo text; data inventory note; the 1.3 decision row replaced

**Verification**:
- Backend: ruff, ruff format, mypy (78 files) pass; pytest 656 passed against the test database, 97% coverage (35 new in `test_curriculum_versions_api.py`: sign-in required, publish and the read-only rule, return to draft, archive and unarchive, refused changes, publishing without a module, deleting drafts, copy forward with lineage, links, tags, mappings and deleted rows left out, role assignments copied and skipped with reasons, editors without `roles.assign`, other roles, diff by lineage, across years and by code; demo tests updated for the draft and for adding the draft to an earlier load); migration drift test passes
- Frontend under Node 24.22.1: lint and typecheck pass; 139 tests pass (11 new in `Versions.test.tsx`: publish, read-only published version, failed change, no actions without rights, copy forward with role ticks, taken year, roles that cannot be copied, delete draft, compare, no differences, failed compare). Running the suite right after the Playwright run made 6 unrelated tests time out once; it passed alone
- Docker: images rebuilt, `migrate` applied `0013` on the existing database, `load-demo` on the existing install added the 2027 draft (the 2026 published version untouched); Playwright (Chromium) against the stack: 49 passed (4 new in `e2e/curriculum-versions.spec.ts`: copy a year forward through the dialog (counts, taken year refused), publish, return to draft and delete it, and the comparison of the demo draft with the published version; axe WCAG 2.2 AA on each dialog and state, light and dark). The existing editing and reorder journeys now run on the draft; the demo data was left as found (2026 published, 2027 draft)
- Found by axe/e2e: the copy dialog's year field was not focused because the form appears after the preview loads (now focused by a ref)
- `mkdocs build --strict` passes
- Not verified here: browsers other than Chromium; screen readers by hand; the CI run on GitHub (runs on push); role copying through the UI with real role holders (covered by API tests and a mocked UI test only)

**Not in this slice**: compare for people who see only part of a version; comparing order, links, tags or mappings; restoring a deleted draft.

**Commit**: `feat: publish rules, copy academic year forward and version diff`

---

### Slice 1.6: Objective Editor
**Status**: Complete

**Deliverables**:
- [x] **Objective API** (ADR 031, `app/services/curriculum_objectives.py`, `app/api/v1/curriculum_objectives.py`): `POST /curriculum-versions/{id}/outcomes` (programme outcome), `POST /modules/{id}/outcomes`, `POST /learning-events/{id}/objectives`, `PATCH`/`DELETE /objectives/{id}`, `GET /modules/{id}/outcome-link-options`, `GET /learning-events/{id}/objective-link-options`, `GET /taxonomy-scales`. No schema change: `Objective` and `ObjectiveLink` already held domain, taxonomy level, status and position
- [x] **Permissions**: `objectives.edit` at the programme, module or session that owns the objective (`objective_scope`); 404 for what the user cannot see, 403 for visible but not allowed, 409 for non-draft versions. Read responses gained `taxonomy_level_id` on objectives and the flags `can_edit_outcomes` (structure), `can_edit_objectives` (module, session)
- [x] **Upward links**: `parent_ids` replaces the links to the outcomes the user may see (and so choose); links to outcomes they cannot see are left alone when they save. Rules from `link_objectives` (same version, broader level, a session objective links to its own module's outcomes or programme outcomes) answer 422. Audit labels `curriculum.objective_create`, `_update`, `_delete`
- [x] **Builder**: Add, Edit and Delete buttons per level in the details panel (named with an excerpt of the wording); one dialog for wording, domain, taxonomy level (grouped by scale), status and the upward-link checkboxes; domain, taxonomy level, status and link chips on each objective; delete confirmation takes focus after deleting. Text from `curriculum.objectives.*` and `terms.*`
- [x] ADR 031; admin guide section "Who can edit objectives"; CLAUDE.md; seven rows in "Decisions to review"
- Tidy: the `_`-prefixed target helpers of `curriculum_edit.py` are public (`Target`, `target_of`, ...) because the objective router reuses them

**Verification**:
- Backend: ruff, ruff format, mypy (80 files) pass; pytest 691 passed against the test database, 97% coverage (35 new in `test_curriculum_objectives_api.py`: sign-in required, director, module coordinator, lecturer, mapper and student, links at each level and their refusals, hidden links kept, null clearing, soft delete, published versions read-only, audit entries, taxonomy scales)
- Frontend under Node 24.22.1: lint and typecheck pass; 149 tests pass (10 new in `Objectives.test.tsx`: no buttons without rights, chips, add with domain/level/links, edit keeping unseen links, no options, failed save, module outcome, programme outcome, delete, institution wording). The first full run had 3 unrelated timeouts under load; the second run passed (as noted in 1.5)
- Docker: images rebuilt; Playwright (Chromium) against the stack with the demo data: 53 passed in one full run (4 new in `e2e/curriculum-objectives.spec.ts`, light and dark: add, change and delete a session objective with domain, level and a link; add a module outcome; edit a programme outcome; axe WCAG 2.2 AA on each dialog and state). Each journey makes its own phase, module, session and programme outcome through the API and deletes them afterwards
- `mkdocs build --strict` passes
- Not verified here: browsers other than Chromium; screen readers by hand; screenshots of the new dialog by eye; a lecturer-only session in the UI (API tests only); the CI run on GitHub (runs on push)

**Not in this slice**: reordering or moving objectives, the objective quality checker and level suggestion (1.7), tags (1.8), choosing links for people who see only their session.

**Commit**: `feat: edit objectives at each level with upward links, domain and taxonomy level`

---
### Slice 1.6a: Review Fixes to Slices 1.3 to 1.6
**Status**: Complete

**Deliverables**:
- [x] **Review of "Decisions to review"**: all earlier rows marked approved (2026-10-26) except the three the owner changed; new rows added for this slice (ADR 032)
- [x] **Outcome sight for narrow roles**: link options for session objectives and module outcomes now include the programme outcomes and the own module's outcomes for anyone who sees part of the version (read-only, link pickers only; the outcome list, module details and structure stay hidden). A lecturer with only a session role can link upward
- [x] **Approval**: new status `ready_for_review`; new permission `objectives.approve` (platform admin, curriculum office, programme director, module coordinator); approving, retiring and leaving those statuses need it, enforced in the service (403); a lecturer rewording an approved objective sends it back to ready for review; `can_approve_objectives` and `can_approve_outcomes` in the read responses; the dialog offers only the statuses the user may set and locks an approved or retired objective's status
- [x] **Unpublish**: new permission `curriculum.unpublish` (curriculum office, programme director, platform admin); returning a published version to draft needs it as well as `curriculum.publish`, and a trimmed reason of 1 to 500 characters stored in the audit log (`curriculum.version_unpublish`); `can_unpublish` in the structure; the dialog asks for the reason
- [x] **Mapping re-check**: `mapping_links.needs_recheck` (migration 0014, additive, default false); set on accepted links when the objective's wording changes, cleared by `confirm_recheck` (service, `mapping.review`, audit `mapping.recheck_confirm`) or `reopen_link`, kept by copy forward; `mappings_to_recheck` on objective reads; "needs re-check" chip (icon and words) in the builder. **Reports (later slices) must show this flag**; there is no mapping screen or HTTP endpoint to confirm yet
- [x] Migration `0014` also widens the objective status CHECK constraint (downgrade turns `ready_for_review` back into `draft`). No data migration for the new permissions: `sync-roles` runs after `alembic upgrade` in the `migrate` service (ADR 012)
- [x] CLAUDE.md: direct SQL that bypasses the audit log only on local test data; approval, unpublish and re-check conventions. Admin guide, data inventory (free-text reasons), e2e README, ADR 032 (ADRs 027, 030, 031 point to it)
- [x] e2e: `lecturer.setup.ts` makes (through the admin API) and signs in a lecturer once and saves the session; new journey `curriculum-lecturer.spec.ts` (a lecturer with only a session role sees the module and programme outcomes, links upward, can set only draft or ready for review; role and fixtures removed through the API). The versions journey now enters the unpublish reason. The editing journeys use the demo's oldest draft instead of "the first version", which a parallel journey could have published

**Verification**:
- Backend: ruff, ruff format, mypy (80 files) pass; pytest 716 passed against the test database, 97% coverage (25 new: approval rules for lecturer, coordinator, director and curriculum office, locked and retired statuses, outcome sight for lecturer and module coordinator and what stays hidden, unpublish reason (missing, blank, too long, trimmed, audited), publish-only role refused, re-check flagging, confirming, reopening and copy forward); migration drift test passes
- Frontend under Node 24.22.1: lint and typecheck pass; 155 tests pass, run alone (6 new: statuses offered with and without approval, locked status, re-check chip, unpublish reason and hidden button)
- Docker: images rebuilt, `migrate` applied `0014` to the existing database; Playwright (Chromium) against the stack with the demo data: 56 passed in a full run (light and dark; axe WCAG 2.2 AA on the new dialogs and states). An earlier full run had one timeout in the new lecturer journey under load (passed alone and in the next two full runs; the notice waits are now 15 s); a first subset run failed on the old "first version" race described above
- `mkdocs build --strict` passes
- Not verified here: browsers other than Chromium; screen readers by hand; screenshots of the new chip and dialogs by eye; confirming a re-check through the UI (no endpoint yet); the CI run on GitHub (runs on push)

**Not in this slice**: mapping screens and reports (they must show `needs_recheck`), an endpoint to confirm a re-check.

**Commit**: `fix: lecturer outcome links, objective approval, unpublish reason and mapping re-check flag`


---

### Slice 1.7: Objective Quality Checker and Level Suggestion
**Status**: Complete

**Deliverables**:
- [x] **Rule-based checker** (ADR 033, `app/services/objective_quality.py`, pure functions): vague verbs and phrases, several verbs, over 40 words, no domain, no upward link (warnings); no known verb, under 3 words, "Students will be able to" lead-in, hard-to-measure words, chosen level differs from the verb's level (notes). Each finding has a code, severity, message and suggestion keys and params. No AI, nothing stored, never blocks saving
- [x] **Verb lists**: per level from `taxonomy_levels.verbs` (pack format); wording rules in a versioned per-language file `app/services/objective_rules/en.json` (other languages: add a file; unknown falls back to English). Level suggestion lists every level and scale the leading verb belongs to; set only when the person clicks
- [x] **API**: live checks `POST .../outcome-checks` (version, module) and `.../objective-checks` (session), `objectives.edit` at the owner's scope, 240 a minute per user; bulk `GET /curriculum-versions/{id}/objective-checks` (visible, non-retired objectives; `objectives.edit` held somewhere)
- [x] **UI**: Quality check box in the objective dialog (debounced 600 ms, polite status line, written severities with icons, level buttons); **Check wording** button and page `/curriculum/versions/:id/quality` with severity, rule and "only with findings" filters, links to the item, and empty, loading, forbidden and error states
- [x] ADR 033, admin guide section, data inventory (Redis counter), CLAUDE.md, six rows in "Decisions to review"

**Verification**:
- Backend: ruff, ruff format, mypy pass; pytest 771 passed against the test database, 97% coverage (37 pure unit tests in `test_objective_quality.py`, 18 API tests in `test_objective_checks_api.py`: sign-in, flags, level suggestion, empty text and nothing saved, length limit, rate limit 429, lecturer scope, student refused, bulk order and visibility, published version not editable)
- Frontend under Node 24.22.1: lint and typecheck pass; 163 tests pass, run alone (9 new in `Quality.test.tsx`). Five older objective tests now read the saved notice by its text, since the dialog's status line is also a status region
- Docker: images rebuilt; Playwright (Chromium) against the stack with demo data: 57 of 60 passed in the first full run (2 new journeys in `e2e/curriculum-quality.spec.ts`, light and dark, axe WCAG 2.2 AA on the panel states and the page); the 3 failures were `accessibility.spec.ts` pages where the app frame did not appear under load, and all 18 tests of that file passed on rerun
- `mkdocs build --strict` passes
- Not verified here: browsers other than Chromium; screen readers by hand (live region behaviour while typing); screenshots by eye; rule quality on real objectives beyond the demo (heuristics, no part-of-speech tagging); the CI run on GitHub (runs on push)

**Not in this slice**: near-duplicate detection (1.15), AI rewrite and classification (1.17), other languages, storing flags on objectives.

**Commit**: `feat: rule-based objective quality checker and taxonomy level suggestion`


---

### Slice 1.8: Tag Lists and Tagging with Inheritance Preview
**Status**: Complete

**Deliverables**:
- [x] **Tag list management** (ADR 034, `app/api/v1/tagging.py`, `app/services/tagging.py`): `GET/POST /tag-lists`, `PATCH/DELETE /tag-lists/{id}`, `POST /tag-lists/{id}/values`, `PATCH/DELETE /tag-values/{id}`; changes need `taglists.manage` (institution scope), reading is open to every signed-in user (active lists only; managers also get inactive lists and usage counts). Key and kind are fixed; a list or tag in use (tagged, or a session's format) cannot be deleted (409), only made inactive. Audit labels `taglist.*`, `tagvalue.*`
- [x] **Tagging items**: `POST /curriculum-items/{module|learning_event|objective}/{id}/tags`, `GET .../tag-preview?tag_value_id=`, `DELETE /taggings/{id}`; `tagging.edit` at the item's scope, 404 for what the user cannot see, 409 for non-draft versions, 422 for removing an inherited tag. Read responses (module, session, programme outcomes) carry `tags` (one entry per tag with direct tagging id and sources) and the flags `can_edit_tags`, `can_edit_outcome_tags`
- [x] **Inheritance**: module to its sessions; objective to the objectives linked beneath it at any depth; chosen when tagging, after a preview of every item reached (new, already has the tag, list not used on this kind of item); every inherited tagging points to the direct tagging it came from; `remove_tagging` now deletes the inherited rows through the ORM so each is audited
- [x] **UI**: details panel shows the tags of the module, session and each objective with the list and, for inherited ones, the source in words (no Remove button); Add tag dialog with the preview and an "also give this tag to N items" box; Remove for direct tags. New admin screen `/admin/tag-lists` (lists, tags, add, edit, make inactive or active, delete with confirmation); Admin menu item also shows for `taglists.manage`
- [x] ADR 034, admin guide page `docs/admin/tag-lists.md` (in the nav), CLAUDE.md conventions, ten rows in "Decisions to review". No schema change, no migration; no personal data added (data inventory unchanged)

**Verification**:
- Backend: ruff, ruff format, mypy (86 files) pass; pytest 811 passed against the test database, 97% coverage (40 new in `test_tagging_api.py`: sign-in required, list and tag management with conflicts, in-use rules, usage and visibility of inactive items, roles that cannot manage, module and objective inheritance with preview and sources, two sources, deleted sources, who may tag, read-only versions, audit counts)
- Frontend under Node 24.22.1: lint and typecheck pass; 191 tests pass (28 new in `Tagging.test.tsx` and `admin/TagLists.test.tsx`)
- `mkdocs build --strict` passes
- Docker: api, worker and web images rebuilt (no migration needed); Playwright (Chromium) `e2e/tagging.spec.ts` against the stack with the demo data: 8 passed, light and dark (tag a module with preview and inheritance and remove it, tag a session, manage a list and tag on the admin screen; axe WCAG 2.2 AA on each dialog and state). axe found one real problem on the way (buttons whose accessible name did not contain their visible text); fixed. A first run of the admin journey timed out on a notice while the machine was busy; its timeout is now 15 s
- Not verified here: the rest of the Playwright suite after this change (only the new spec was run); browsers other than Chromium; screen readers by hand; screenshots by eye; the CI run on GitHub (runs on push). The saved e2e admin session had expired and the old password was not at hand, so a new platform admin `e2e.tagging@example.org` was created on the local stack for the run

**Not in this slice**: programme-level tags, re-applying a tag to items linked or added later, reordering tags, tag filters in search and reports (1.20 and the reports slices), tag import (1.26).

**Commit**: `feat: manage tag lists and tag items with inheritance preview and source`

### Slice 1.9: Minimal Assessments and the Credits and Notional Hours Check
**Status**: Complete

**Deliverables**:
- [x] **Assessments** (ADR 035; `app/models/assessment.py`, `app/services/assessments.py`, `app/api/v1/assessments.py`, migration 0015): `Assessment` (module, name, method tag, weight, timing, learner time), `AssessmentItem` (label, marks) and `AssessmentItemObjective`; all `Audited`, changed through ORM objects, soft delete. Endpoints `POST /modules/{id}/assessments`, `PATCH/DELETE /assessments/{id}`, `POST /assessments/{id}/items`, `PATCH/DELETE /assessment-items/{id}`, `GET /assessment-methods`, `GET /modules/{id}/assessable-objectives`. `curriculum.edit` at the module, 404 for what the user cannot see, 409 for non-draft versions, 422 for a method outside an assessment-method list or an objective outside the module and its sessions. A method in use cannot be deleted from its tag list. Module detail now carries `assessments`, `can_edit_assessments` and `hours`
- [x] **Copy, copy forward, delete, diff**: copying a module or phase copies assessments, items and the links to the copied objectives; copy forward does the same and records `based_on_id` on every assessment and item; deleting a module or a draft version deletes them; the version diff has an `assessment` kind (name, method, weight, timing, time, number of items)
- [x] **Credits and notional hours check** (`app/services/credit_check.py`, pure rules plus a gatherer): per module (contact + self-study + assessment time against credits x hours per credit, tolerance, `ok/under/over/no_credits`), per `year` phase, per NQF level, and findings against the programme and qualification type. Figures are the new `credits` institution settings section (`CreditPolicy`: 10 hours, 10%, 120 credits per year, optional exit-level minimum). `GET /curriculum-versions/{id}/credit-check` (whole version visible; 404 otherwise). Advice only: nothing blocks saving
- [x] **UI**: module details show an Assessments section (add, edit, delete assessments and items, link items to objectives with a checkbox list) and the planned hours in words with an icon (ochre for attention, never colour alone); new **Credits and hours** page (`/curriculum/versions/:id/credits`, button "Check credits" in the version bar) with summary and findings, years, NQF levels and every module; compare page lists assessment changes
- [x] Demo: six assessments with 11 items linked to the modules' outcomes (copied into the 2027 draft with lineage)
- [x] ADR 035, admin guide `docs/admin/assessments-and-credits.md` (in the nav), `docs/admin/basics.md` (credits settings), CLAUDE.md conventions, twelve rows in "Decisions to review". No personal data added (the data inventory already covers `created_by_id` on every table)

**Verification**:
- Backend: ruff, ruff format, mypy (91 files) pass; pytest 868 passed against the test database, 97% coverage (57 new: `test_assessments_api.py` for sign-in, create/update/delete, methods, bad values, linking rules, deleted objectives, read-only versions, roles, copying, copy forward lineage, the diff, a method in use; `test_credit_check.py` for the rules, the settings and the API; demo assertions in `test_demo.py`)
- Frontend under Node 24.22.1: lint and typecheck pass; 208 tests pass (17 new in `Assessments.test.tsx`)
- `mkdocs build --strict` passes
- Docker: api, worker, web and migrate rebuilt (migration 0015 ran on the stack); Playwright (Chromium), the whole suite: 70 passed in light and dark, including the new `e2e/assessments.spec.ts` (add an assessment and an item linked to an outcome, hours advice changes, credits page, edit, delete; axe WCAG 2.2 AA on each screen, dialog and state). The saved e2e sessions were still valid, so no account was created
- Not verified here: the demo data on the Docker stack was not reloaded, so the new demo assessments were checked in the backend tests only (the e2e journeys make their own data); browsers other than Chromium; screen readers by hand; screenshots by eye; the CI run on GitHub (runs on push); the migration downgrade (written, not run)

**Not in this slice**: reordering assessments and items, a settings screen for the credit figures (Slice 1.30), assessment blueprints and "never assessed" alerts (phase 3), the assessment methods coverage report (1.24), a renamable term for "assessment", assessments in the copy-forward preview counts.

**Commit**: `feat: add minimal assessments and the credits and notional hours check`

### Slice 1.10: Framework Pack Import from the Screen, Pack Format 2 and Templates
**Status**: Complete

**Deliverables**:
- [x] **Pack format version 2** (ADR 036, `packs/schema/framework-pack.schema.json`, `app/services/packs.py`): optional `format_version` (no value means 1, so existing packs are unchanged), `crosswalks` from an earlier imported version, `tag_lists`, cross-references to items of other imported frameworks (`to_framework`, `to_version`), type `equivalent`, and `metadata.template`. `check_pack` lists every problem with its location; `resolve_pack` checks the database (other frameworks and versions, existing scales and tag lists). `import_pack` now adds items level by level in bulk (20 000 items in about 20 s measured, with audit rows), still as ORM objects
- [x] **API** (`app/api/v1/framework_packs.py`): `POST /framework-packs/preview` (raw JSON body, 413 over `PACK_MAX_UPLOAD_MB`, problems as 200 with `valid: false`, a Redis token for 30 minutes when valid, rate limited to 20 a minute), `POST /framework-packs/import` (token, optional `activate`; checks again; audit label `framework.import`), `GET /framework-packs/templates` and `.../{name}`. `frameworks.manage` for the instance; a pack with tag lists also needs `taglists.manage`
- [x] **Screen** `/import` ("Import and export"): choose a file, check, read the preview (details, licence note, counts, notes, first 200 items, activate checkbox), confirm, see the result; error table; states for checking, importing, invalid, failed and done; blank-template downloads. Other users still see the placeholder page
- [x] **Templates** (structure only, `packs/templates/` with an identical copy in `backend/app/pack_templates/`, tested): `hpcsa-core-competencies`, `nqf-level-descriptors` (ten levels), `graduate-attributes`, `mesh-subset`. No competency text, descriptor text or MeSH term is included
- [x] New settings `PACK_MAX_UPLOAD_MB` and `PACK_MAX_ITEMS` (config, `.env.example`, configuration guide); data inventory (Redis keys); admin guide `docs/admin/framework-packs.md` (in the nav); ADR 036; CLAUDE.md; ten rows in "Decisions to review"

**External checks**: NLM data terms page (credit line, no endorsement, currency statement) read on 2026-10-26; NLM XML page confirmed the `DescriptorUI` field. **Not verified**: the MeSH licence page itself; the SAQA site could not be opened (certificate error), so "ten NQF levels" rests on search results quoting the 2012 gazetted level descriptors and on the brief; the HPCSA document was not consulted at all, so that template claims nothing about its structure; NQF descriptor category names were not used. These are stated in the ADR, the admin guide and the template licence notes.

**Verification**:
- Backend: ruff, ruff format, mypy (93 files) pass; pytest 927 passed against the test database, 97% coverage (new: `test_pack_format_two.py` for format versions, new section problems, crosswalks, tag lists, references to other frameworks, bulk import, templates identical to their bundled copies, schema enumerations in step with the models; `test_framework_packs_api.py` for sign-in, permissions, preview and import, token use once and per user, size and item limits, bad files with line and column, byte order mark, templates, rate limit, tag list permission)
- Frontend under Node 24.22.1: lint and typecheck pass; 219 tests pass (11 new in `importing/PackImport.test.tsx`)
- `mkdocs build --strict` passes
- Docker: images rebuilt (`up -d --build --wait`, no migration needed); Playwright (Chromium), the whole suite: 76 passed in light and dark, including the new `e2e/framework-import.spec.ts` (check, preview, import, repeat refused; a file with problems; a downloaded blank template refused; axe WCAG 2.2 AA on each state). The saved e2e sessions were still valid; no account was created
- Not verified here: browsers other than Chromium; screen readers by hand; screenshots by eye; a very large file through the browser (the 20 000 item timing is a backend measurement, not a browser run); the pack JSON schema file validated with a JSON Schema library (not a project dependency; only its enumerations are tested); the CI run on GitHub (runs on push)
- Left on the local stack: each e2e run imports two small frameworks (`e2e-light-...`, `e2e-dark-...`) and a tag list for each; there is no delete endpoint yet (Slice 1.11)

**Not in this slice**: Excel import of frameworks (1.26), YAML, the framework library and browser (1.11), editing or deleting a framework, AI migration of mapping links across a crosswalk (phase 2).

**Commit**: `feat: import framework packs from the screen with pack format 2 and blank templates`

### Slice 1.10a: Review Changes to 1.7-1.10 (Tag Passing, Faculty Tag Lists, Exit-Level Credits, E2E Hygiene)
**Status**: Complete

Requested by the product owner after reviewing Slices 1.7 to 1.10.

**Deliverables**:
- [x] **Pass a tag on to newer items** (ADR 034; `pass_on_preview`, `pass_on`, `not_reached_counts` in `app/services/tagging.py`): "apply once" stays. A direct tag on a module or a programme/module outcome now carries `not_reached` (items below it, added or linked later, that lack the tag); the details panel shows a notice with the count and a **Pass it on** button that previews exactly like Add tag (`GET /taggings/{id}/pass-on-preview`) and then applies (`POST /taggings/{id}/pass-on`, `tagging.edit` at the item, draft versions only, audit `tagging.pass_on`, ORM rows)
- [x] **Faculty-scoped tag lists** (ADR 015, ADR 034; migration 0016 `tag_lists.faculty_id`): the brief's roles table gives the curriculum office tag lists at faculty scope. A list is institution-wide (null) or one faculty's. `taglists.manage` at a faculty manages that faculty's lists; at the instance every list; a faculty manager cannot create or change institution-wide or other faculties' lists. Lists are visible to people with a role in that faculty (or an instance role); the session format and assessment method choices follow the same rule; a faculty list tags only items of its faculty (422). New `GET /tag-lists/places`; list reads carry `faculty_id`, `faculty_name`, `can_manage`. The tag lists screen shows who keeps each list, hides change buttons on lists the user cannot change and asks "Kept for" when creating. Navigation already showed the Admin item for any-scope `taglists.manage`; the API now agrees
- [x] **Exit-level minimum credits** (ADR 035; migration 0016 column `qualification_types.min_exit_level_credits`, data migration 0017 with a table stub): Bachelor's (360) at least 120 credits at NQF 7 and professional Bachelor's (480) at least 120 at NQF 8, with the source in each row's notes. `credit_check.py` uses the institution's setting when set, else the type's figure at the type's own exit level. The Credits page shows the figure with a "verify against the current CHE and HEQSF documents" note; the admin guide explains it
- [x] **E2E hygiene** (ADR 037): `DELETE /frameworks/{id}` (unused frameworks only, audited) and `DELETE /users/{id}` (anonymising soft delete, audited) so journeys can clean up through the API instead of SQL; the framework-import and tag-list journeys remove what they create (also on failure); a Playwright teardown project deletes the test lecturer after every run; new journey for passing a tag on. Chosen over a separate e2e database or compose project because that would need a second stack, ports, demo load and admin account to keep in step, while the deletes are small, permission-guarded and audited
- [x] Found on the way: the audit log insert failed when one flush mixed creates, updates and deletes (rows with different keys in one executemany); entries are now inserted per shape (regression test)
- [x] Docs: ADR 015, 034, 035, new ADR 037 (index updated), `docs/admin/tag-lists.md`, `docs/admin/assessments-and-credits.md`, `docs/privacy/data-inventory.md` (account deletion), `frontend/e2e/README.md`, CLAUDE.md

**Source check (item 3)**: the Stellenbosch University "Guidelines on qualification types" (July 2022) could **not** be fetched (its URL redirects to the university home page). A web search only showed that the document exists and that a related guideline attaches the 120 credits at NQF 7 to the final-year block of the professional (480-credit) degree; it did not confirm the wording for the 360-credit degree. The figures are therefore entered as given by the product owner and are **not verified**; the notes, the UI and the docs say to verify them against the current CHE/HEQSF documents.

**Status (2026-10-27)**: the exit-level figures stay flagged "verify" until the product owner has confirmed them with the institution's QA office; do not remove the notice before then.

**Verification**:
- Backend: ruff, ruff format --check, mypy (94 files) pass; pytest 955 passed against the test database (container `ocmp-test-db`, port 55432), 97% coverage. New: `test_tagging_faculty_and_pass_on.py` (faculty managers keep their faculty's lists only, cannot touch institution-wide or other faculties' lists, places, visibility per role, format choices, faculty list on items of another faculty refused, newer sessions and objectives counted, previewed and passed on, rules for 404/409/422/403, sign-in required), `test_cleanup_deletes.py` (framework and account delete rules, audit of a mixed flush, seeded exit-level credits), exit-level cases in `test_credit_check.py`; the migration round trip (downgrade to base and up) and the models-match-migrations test pass with 0016 and 0017
- Frontend under Node 24.22.1: lint and typecheck pass; 225 tests pass (6 new: faculty chips and read-only lists, creating a list for a faculty or choosing where, pass-on notice and dialog, notice hidden when nothing is missing or the person cannot tag)
- `mkdocs build --strict` passes
- Docker: all images rebuilt (`up -d --build --wait`; migrations 0016 and 0017 ran on the stack). Playwright (Chromium), the **whole suite: 79 passed** in light and dark, including the new pass-on journey and the cleanup teardown. axe found one real problem in the new button (its accessible name did not contain its visible text "Pass it on"); fixed and rerun. A first full run had exactly those two failures (77 passed)
- After the full run the stack was checked with a read-only census through the ORM: no `e2e-*` frameworks, no stray tag lists, no test accounts except the operator's `e2e.admin@example.org`, no leftover phases (6 modules and 2 versions: the demo)
- Not verified here: browsers other than Chromium; screen readers by hand; screenshots by eye; the CI run on GitHub (runs on push); the exit-level figures against their source (see above); a faculty-scoped user in the browser (faculty manager screens are covered by unit and API tests only, because the demo has no faculty-scoped account); performance of the not-reached count on a very large tagged tree
- The saved e2e admin session had expired and its password was not at hand, so a temporary platform admin `e2e.tmp@example.org` was created on the local stack with the CLI for the runs and **deleted again** at the end (through the new delete service); the saved e2e session files were removed. To run the suite again, sign in with `e2e.admin@example.org` and its password

**Local stack cleanup**: through the ORM and the new delete services (an `audit_operation("e2e.cleanup")` script run inside the api container, not SQL), removed the account `e2e.tagging@example.org`, the stale `e2e.lecturer@example.org`, six `e2e-light-*`/`e2e-dark-*` frameworks and their seven tag lists and the leftover `screen-light-*` list. `e2e.admin@example.org` (made by the operator for the tests) was kept.

**Not in this slice**: faculty-scoped framework management (`frameworks.manage` stays instance-level), a screen to delete frameworks (1.11), the full POPIA export/deletion flow, a UI for editing qualification types.

**Commit**: `feat: pass tags on to newer items, faculty tag lists, exit-level credits and e2e cleanup`

### Slice 1.10b: Demo Faculty Curriculum-Office Account and Faculty Tag List
**Status**: Complete

So faculty-scoped tag lists (1.10a) can be checked in a browser, which the demo could not do before.

**Deliverables**:
- [x] Demo data: a faculty-scoped list `fhs-clinical-skills` (kind custom, tags modules and sessions, three values) kept for the demo faculty, and an `office_user` entry (`curriculum.office@example.org`, an example.org address) in `bsc-health-sciences-demo.json`
- [x] `load_demo` creates the account through `create_local_user` and `assign_role` (curriculum office at the demo faculty only, audited as `demo.load`). **Password handling**: no demo account existed before, so no password is in the data or the code; the account is made only when `OCMP_DEMO_OFFICE_PASSWORD` is set (the same pattern as `OCMP_ADMIN_PASSWORD`, checked against the password policy). Without it nothing is made. Running `load-demo` again with it set adds the faculty list and the account to an install loaded earlier; with nothing to add a second load is still refused
- [x] Tests (`test_demo.py`, `test_cli.py`): no account without a password; the account holds `taglists.manage` at the faculty only (not at the instance, no `frameworks.manage`), covers the faculty list and not institution-wide lists; added to an earlier full load; counts now four tag lists. The API rules for faculty managers are already covered by `test_tagging_faculty_and_pass_on.py`
- [x] Docs: install guide (demo section), `docs/admin/basics.md`, `docs/admin/tag-lists.md`, `docs/privacy/data-inventory.md`
- Not done: a Playwright journey for the faculty user. It would need a second saved session and a known password for a persistent account, which the e2e hygiene rules (ADR 037: journeys leave nothing behind, no sign-in inside tests) would have to extend; skipped

**Verification**: ruff check, ruff format --check and mypy (94 files) pass; the related tests pass against the test database (100 passed: `test_demo`, `test_cli`, tagging, faculty tag lists, cleanup). `mkdocs build --strict` passes. **Not verified**: the whole backend suite (a full run on this loaded machine did not finish; 269 tests had passed with none failing when it was stopped); the frontend was not touched, so its checks and the Playwright suite were not run; the account was not tried in a browser or in the Docker stack (the running api image was not rebuilt)

**Commit**: `feat: add a faculty-scoped curriculum-office demo account and faculty tag list`

### Slice 1.11: Framework Library, Tree Browser with Search and "Where Mapped"
**Status**: Complete

**Deliverables**:
- [x] **Read API** (ADR 038; `app/api/v1/frameworks.py`, `app/services/framework_browse.py`, `app/schemas/frameworks.py`; no migration): `GET /frameworks` (versions with item, top-level and level counts, source, licence note, status, `can_manage`), `GET /frameworks/{id}/items` (a window of the children of one parent, 100 by default, 200 at most, with `offset` and `total`, `child_count` and `mapped_count`), `GET /frameworks/{id}/search` (code or words, case-insensitive, with the path above each match), `GET /frameworks/{id}/items/{item_id}` (path with each ancestor's place among its siblings) and `.../mappings` (where mapped, read only). `curriculum.view` or `frameworks.manage` at any scope reads (403 otherwise); a missing, deleted or foreign framework or item is 404
- [x] **"Where mapped" respects what the user may see** (ADR 027): the same `visible_version` rules as the curriculum screens decide which versions (drafts only with `curriculum.view`), programme outcomes (whole version only), module outcomes (module) and session objectives (session) show; hidden links are left out of lists and of every count. Rejected links, deleted objectives, modules, sessions, versions and programmes are left out. No reviewer names are returned
- [x] **Screens** (`frontend/src/frameworks/`): the library at `/frameworks` (cards per framework with kind, status, size and version count; details with description, source, licence note, size, versions; Browse and, for `frameworks.manage`, Delete with a confirmation and the server's refusal in words; link to the blank templates on the Import page; empty, loading and error states) and the browser at `/frameworks/:id` (accessible lazy tree: roving tab stop, Up/Down/Left/Right/Home/End/Enter/Space, true `aria-posinset`/`aria-setsize`, "Show more" and "Show earlier" rows that the keyboard reaches; search with results, counts and "Show in tree" that opens the tree at the item and moves focus to it; item details with breadcrumb path; where-mapped list with status in words, coverage, depth, "wording changed" and "reviewers disagree" flags and links into the curriculum). The selected item is in the address (`?item=`)
- [x] Docs: ADR 038, `docs/admin/frameworks.md` (in the nav), ADR 037 consequence updated, CLAUDE.md conventions, six rows in "Decisions to review". No personal data added or moved (the data inventory is unchanged): the screens read frameworks and objectives, and no reviewer or author names are returned

**Performance (20 000 items, measured on the Docker stack while the backend test suite ran in the background, so times are on the high side)**: a pack of 20 000 items (20 groups, 400 subgroups, 19 580 leaves; 1.8 MB) previewed in 0.8 s and imported in 23 to 26 s; then library 52 ms, top level 48 ms, children of a group 48 ms, children of a subgroup 62 ms, search by code 127 ms, search by words with 19 580 matches 186 ms (first 50 returned), item detail 61 ms, where mapped 30 ms. Search is a substring scan of one framework; no index was added
**Verification**:
- Backend: ruff, ruff format --check, mypy (96 files) pass; the whole pytest suite passed against the test database (container `ocmp-test-db`, port 55432): 976 passed, 97% coverage, 23 minutes on this machine. New: `test_framework_browse_api.py` (18 tests: library counts, versions and licence note, deleted frameworks hidden, 401 and 403 (student), lecturer reads but cannot manage, tree order and child counts, windows and the 200 limit, 404 for foreign items and parents, detail path and sibling positions, a 1 500 item flat framework in windows, search by code and text, wildcard characters as plain text, empty search refused, search pages and mapped counts, where mapped for the office, a module role, a session role, a role in another programme, deleted rows left out, re-check flag)
- Frontend under Node 24.22.1: lint and typecheck pass; 247 tests pass (22 new in `frameworks/Frameworks.test.tsx`: library cards, details, links, import/delete only for managers, confirm and delete, refusal in words, empty and error states; tree roles and levels, keyboard open/close/move, Home/End, selection, where mapped with links and flags, opening to an item in the address, loading more, search, nothing found, show in tree with focus, clear, empty framework, unknown framework, failed load). A first run of the whole suite with the backend suite running beside it had seven timeouts (5 s) in older curriculum and setup tests; with the machine quiet all 247 passed
- `mkdocs build --strict` passes
- Docker: all images rebuilt (`up -d --build --wait`, no migration needed). Playwright (Chromium), the **whole suite: 85 passed** in light and dark, including the new `e2e/frameworks.spec.ts` (browse the demo framework by keyboard, see where an item is mapped, search, show in tree, nothing found; a 130 item pack that opens in windows and an item far down opened from a search; deleting an unused version after a confirmation), with axe WCAG 2.2 AA on each screen, state and the dialog in both themes. axe found one real problem in the new "Show more items" row (its accessible name did not contain its visible text); fixed and rerun. A first full run had one failure, the long demo journey timing out at 30 s beside the other journeys; its timeout is now 90 s and the second full run passed
- After the runs, a read-only census through the ORM (script run in the api container): the only live framework is the demo one, no `e2e-*` or `perf-*` frameworks, no test accounts except the operator's `e2e.admin@example.org`, tag lists unchanged. The saved session was missing, so `auth.setup.ts` signed in as `e2e.admin@example.org` from `frontend/e2e/.env.local`; the test lecturer is made and deleted by the suite itself; no other account was created
- Not verified here: browsers other than Chromium; screen readers by hand; screenshots by eye; the CI run on GitHub (runs on push); a user with only a module or session role in the browser (covered by API tests and the unit tests with mocked data, not by a Playwright journey: the e2e rules allow no persistent second account); the library with several versions of one framework in the browser (unit tests only); the demo's faculty tag list is not on the running stack (it predates 1.10b) which does not affect this slice
- The 20 000 item test pack was imported and then deleted through the API (`DELETE /frameworks`); as designed (ADR 037) deleting hides the version and keeps its 20 000 item rows, so the local database holds them until a purge exists

**Not in this slice**: creating or changing mappings (1.12), coverage bars and counts per group (1.24), the crosswalk and migration panel (phase 2), Excel template buttons (1.26), cross-references between items, meaning-based search (1.15), purging deleted frameworks, editing a framework, a persistent second e2e account for module-scoped journeys.

**Commit**: `feat: add the framework library, tree browser with search and where-mapped view`

### Slice 1.12: Mapping Workspace (Manual Linking, Coverage 0-5 and Depth with Help Text)
**Status**: Complete

The wording of the scale was not in the brief; the product owner supplied it on 2026-10-27 (see ADR 039 and the "Decisions to review" rows).

**Deliverables**:
- [x] **API** (ADR 039; `app/api/v1/mapping.py`, `app/services/mapping_links.py`, `app/services/mapping_workspace.py`, `app/schemas/mapping.py`): `GET /curriculum-versions/{id}/mapping` (the objectives the user may see, each with its non-rejected links and `can_edit` / `can_review` at its own scope, plus `editable` and `four_eyes`), `POST /objectives/{id}/mapping-links`, `PATCH` and `DELETE /mapping-links/{id}`, `POST /mapping-links/{id}/recheck`. `mapping.edit` at `objective_scope` (roles higher up count); an objective or link the user cannot see is 404; non-draft versions are 409; audit labels `mapping.link_add`, `mapping.link_update`, `mapping.link_remove`
- [x] **Status handling**: a reviewer's link is accepted at once (second review in four-eyes mode, also for an edit of an accepted link); anyone else with `mapping.edit` makes a suggestion; an edit is decided again; a rejected pair is reopened; `needs_recheck` is cleared only by "Still fits" (existing `confirm_recheck`, `mapping.review`); removing an AI or migrated link rejects it instead of deleting it
- [x] **Depth gets a fourth value, `not_applicable`** (migration `0018` replaces the CHECK constraint; `DepthMatch` is the one enumeration, used by the schemas and the demo loader; the pack schema holds no links, so it is unchanged). The brief's list (three values) is updated
- [x] **Screen** (`frontend/src/mapping/`, route `/mapping/:versionId`): three panes as in the mockup (objectives with module, phase and "without links" filters; the selected objective's links with coverage in words and five segments, depth, status and flags; the framework chooser with the 1.11 tree and search through the new `FrameworkExplorer`, and the item panel with a "Link to the selected objective" button). A dialog sets coverage 0 to 5 and depth with the definitions, an optional reason and a sentence on what saving does to the link's status. The "?" gives the owner's help text word for word plus every level and depth defined. No drag and drop, so every action works by keyboard and single click. Read-only banner for published versions; empty, loading and error states. Phase 2 items of the mockup are not shown
- [x] Docs: ADR 039, `docs/admin/mapping.md` (in the nav), `docs/PROJECT_BRIEF.md` (four depth values), CLAUDE.md, nine rows in "Decisions to review". No personal data added or moved (the data inventory is unchanged): no reviewer or author names are returned, and the audit entries use the existing actor column

**Verification**:
- Backend: ruff check, ruff format --check, mypy (100 files) pass; the whole pytest suite passed against the test database (container `ocmp-test-db`, port 55432): 1005 passed, 97% coverage, 9 minutes. New: `test_mapping_workspace_api.py` (29 tests: listing and permissions per scope, rejected links hidden, 404 for what is not visible, published version read only, reviewer link accepted and audited, four-eyes second review, suggestion by an editor who cannot review, duplicate pair 409, rejected pair reopened, value validation, unknown item, deleted framework, scope rules for module, session and programme objectives, 403 without `mapping.edit`, edits (flag kept, four-eyes, unchanged, non-reviewer reset), removal (deleted, AI suggestion rejected), re-check confirmation and its permission); the existing migration round trip test runs `0018` up and down
- Frontend under Node 24.22.1: lint and typecheck pass; 258 tests pass (11 new in `mapping/Mapping.test.tsx`: opening the remembered version, links with coverage in words, filters, the help text word for word with all levels and depths, linking with validation messages and the exact request, four-eyes wording, no linking for read-only objectives or versions, editing from current values, confirm before removing, the re-check confirmation)
- `mkdocs build --strict` passes
- Docker: all images rebuilt (`up -d --build --wait`); `migrate` applied `0018`. Playwright (Chromium), the **whole suite: 87 passed** (85 before + the new `e2e/mapping.spec.ts` in light and dark), with axe WCAG 2.2 AA on the workspace, the open help, the link dialog (and its validation messages) and the remove dialog in both themes. The journey makes its own phase, module, objective and a small framework through the API, links, changes and removes a link, and removes everything afterwards (links first). axe found one real problem: the "Show item" button's accessible name did not contain its visible text; fixed. One earlier full run had one failure in `curriculum-versions.spec.ts` (the compare journey, "Loading" at the 5 s limit while two versions journeys ran in parallel on the loaded machine); that spec passes alone with one worker and the whole suite passed on the second run, so I take it for the known parallel flake of that spec, not for this slice, but I did not investigate it further
- After the runs, a read-only census through the ORM: live frameworks are only the demo one; no `MP-`/`OB-` modules or e2e phases left; accounts are the operator's `e2e.admin@example.org` plus the two that were already there; no human-made mapping link remains. 442 mapping links point to soft-deleted objectives (copies made by the versions journey, from before this slice) and stop any framework they point at from being deleted; they are of the demo framework only
- **Not verified here**: the Charité scale citation (Theurich et al. 2025, GMS J Med Educ 42(4):Doc46) was supplied by the product owner and was **not fetched**; browsers other than Chromium; screen readers by hand; screenshots by eye; the CI run on GitHub (runs on push); a user with only a module or session role in the browser (API tests and mocked unit tests cover it, not a Playwright journey); four-eyes mode in the browser (API tests and unit tests only); the "Still fits" button against a real flagged link in the browser (unit and API tests only); a suggestion by a non-reviewer in the browser (API tests only)

**Not in this slice**: the review queue, bulk accept, keyboard shortcuts and the sidebar count (1.13), AI suggestions (1.16), coverage reports, the weighted coverage calculation and heatmaps (1.21), choosing the item first and then picking objectives, filtering by tag or taxonomy level, a count of unmapped objectives per module, purging the links of deleted objectives.

**Commit**: `feat: add the mapping workspace with manual linking, coverage 0 to 5 and depth`

### Slice 1.13: Review Queue (API and Screen, Keyboard Shortcuts, Bulk Accept, Four-Eyes, Sidebar Count)
**Status**: Complete

**Deliverables**:
- [x] **API** (ADR 040; `app/api/v1/mapping_review.py`, `app/services/mapping_review.py`, `app/schemas/mapping_review.py`; no migration): `GET /mapping/review-queue` (one pile per call: first review, second review, re-check; filters version, framework, module and confidence; sort by confidence either way or by module; paging 50 by default, 100 at most; with progress, counts per pile, filter choices and the four-eyes setting), `GET /mapping/review-queue/count`, `POST /mapping-links/{id}/review` (accept, reject or second review, with corrected coverage and depth when accepting, and the `expected_status` the person saw: 409 if the link moved on), `POST /mapping/review-queue/bulk-accept` (with `dry_run`). First review needs `mapping.review`, second review `mapping.second_review`, at the objective's scope; only draft versions the user may see; a link the user cannot see is 404; no reviewer or author names are returned. Audit labels `mapping.review_first_accept`, `..._first_accept_edited`, `..._second_accept`, `..._second_accept_edited`, `mapping.review_reject`, `mapping.review_send_second`, `mapping.review_bulk_accept`
- [x] **Four-eyes in the service** (`mapping.review_link`): first accept goes to a second review; the second reviewer must differ from the first reviewer **and from the author of a hand-made link** (new); overturning the first decision sets `needs_discussion`; the queue leaves out, and does not count, links the user may not second
- [x] **Bulk accept rules**: at least 80% confidence; only first-pile suggestions with confidence, coverage and depth; never a person's suggestion, a second review or a re-check; never the user's own; within the screen's filters; at most 200 per action, most confident first; in four-eyes mode only a first review; counted first, rules shown, one audit operation
- [x] **Screen** (`frontend/src/review/`, `/mapping/review`, the "Review queue" menu item): progress card (reviewed of total, accepted, rejected, second review, waiting, bar also in words), filters (pile with counts, confidence, module, version and framework when there is a choice, order), cards, and the selected suggestion (objective with the evidence marked, suggested item with its group, reasoning, confidence, coverage 0 to 5 and depth to correct, notes on what accepting does, first decision shown to a second reviewer, re-check and discussion notices), **Accept / Second review / Reject / Skip**, paging, empty, loading and error states, a status line for each result. Suggestions by people render without a confidence bar. **Shortcuts** A, R, E, S, 2 work only while focus is inside the list or details, never in text fields or with Ctrl/Alt/Meta, are listed on the page beside a switch that turns them off (kept in the browser), and every action is a button (`aria-keyshortcuts` set). The **sidebar count** shows the total waiting for the user, in words for screen readers. Phase 2 items of the mockup are not shown
- [x] Docs: ADR 040 (and ADR 039's consequence line), `docs/admin/review-queue.md` (in the nav), mapping guide pointer, CLAUDE.md convention, eleven rows in "Decisions to review". The data inventory is unchanged: the queue returns no personal data (no names), writes no new personal column, Redis key or log field; audit entries use the existing actor column

**Verification**:
- Backend: ruff check, ruff format --check, mypy (103 files) pass; the whole pytest suite passed against the test database (container `ocmp-test-db`, port 55432): 1040 passed, 97% coverage, 20 minutes. New: `test_mapping_review_api.py` (35 tests: sign-in required; a module reviewer sees only their module; the office sees every draft suggestion; filters, sorting, paging and the 100 limit; no review permission means an empty queue; progress and counts; the re-check pile and "Still fits"; accept audited with accept method and first reviewer; edit and accept; reject and second review; a moved-on link is 409; decided links are 409; corrections only with an accept; accept needs coverage and depth; 422 for bad requests; 404 outside the user's scope and for rejected links; 403 for a user who sees but may not review; published version 409; a person's suggestion reaching the reviewer with its author recorded; four-eyes with two reviewers; overturning flags discussion; a second review needs the permission; the author of a hand-made link counts as first reviewer; the author of a suggestion cannot second; "unsure" without four-eyes; bulk accept (dry run, scope, floor, cap, four-eyes is a first review, people's suggestions left alone, no permission))
- Frontend under Node 24.22.1: lint and typecheck pass; **280 tests pass** (22 new in `review/Review.test.tsx`: list with progress, evidence, reasoning and the sidebar count; A, R, 2, E and S; modifiers, other keys and filters never act; the switch and its stored choice; no accept without coverage and depth; a person's suggestion; four-eyes wording; the second pile with the first decision and no second-review button; the re-check pile; a 409; bulk accept counted and confirmed, nothing eligible, four-eyes wording; filters sent to the server; empty, error and no-access states; `shortcutFor`). The full suite had timeouts (5 s) in older curriculum and mapping tests when the machine was busy (other programs were using 60 to 80% of the CPU); `Quality.test.tsx` passed alone, and the whole suite passed (23 files, 280 tests) with `--maxWorkers=2`, so I take those for load, not for this slice
- `mkdocs build --strict` passes
- Docker: all images rebuilt (`up -d --build --wait`, no migration). Playwright (Chromium), the **whole suite: 89 passed** with `--workers=1` (87 before + the new `e2e/review.spec.ts` in light and dark). The journey uses the test lecturer with a custom role (mapping, no review) on its own module to suggest three links through the API, then as the admin: sidebar count; the bulk dialog and its count (nothing eligible: people's suggestions have no confidence); edit and accept by keyboard (E, arrow, A); reject with R; second review with 2 and the empty "second review" pile for the person who gave the first review; a changed objective wording putting the link in the re-check pile; shortcuts switched off (the key does nothing, the button works) and on again; axe WCAG 2.2 AA at each state in both themes. axe found one real problem: the Accept button's accessible name ("Accept the link to ...") did not contain its visible text ("Accept A"); the names now come from the visible text. One earlier run of the new journey failed on a custom role key with hyphens (the API wants letters, digits and underscores); it left a phase, module and framework behind, which I removed through the API, and the journey's fixture now registers each piece for clean-up as it is made
- After the runs, a read-only census through the API: the only live framework is the demo one; the draft and published demo versions hold only their demo phases and modules (no `RV-`, `MP-` or other e2e modules); no custom roles; accounts are the operator's `e2e.admin@example.org` plus the two that were already there (the test lecturer is made and deleted by the suite); the review queue is empty (no suggestion left); no e2e tag lists
- **Not verified here**: a second reviewer actually deciding in the browser (needs a third account: only the admin and the test lecturer exist in the e2e rules; API and unit tests cover it, and the browser shows the first reviewer's own pile empty); bulk accept with real confident suggestions in the browser (there is no AI yet to make links with a confidence); four-eyes mode in the browser (it is an institution-wide setting that parallel journeys would feel); browsers other than Chromium; screen readers by hand (including how NVDA or JAWS treat the letter keys); screenshots by eye; the CI run on GitHub (runs on push); the queue with thousands of waiting suggestions (the filtering is in memory, see the decision row)

**Not in this slice**: AI suggestion generation (1.16), a list of decided links and reopening a rejected link, reassigning or assigning review work (`review_assignments` is unused), a per-user "my queue" restriction to assigned modules beyond permissions, undo of a decision, remapping shortcuts, a version button in the header of the queue page.

**Commit**: `feat: add the review queue with keyboard shortcuts, bulk accept and second review`


### Slice 1.14: AI Provider Layer, Privacy Guard, Encrypted Keys, Budgets, Local-only, Admin AI Settings
**Status**: Complete

The layer, the guard, the settings and the screen. **No feature uses it yet** (mapping, rewrite, extraction and embeddings are 1.15 to 1.18): the only callers are a minimal internal `ai_gateway.complete()` and the admin's "Test connection" button.

**Deliverables**:
- [x] **Providers** (`backend/app/ai/providers/`, ADR 042): interface `LLMProvider.generate_structured(GuardedRequest)`; `NullProvider` (default, no network code), `AnthropicProvider`, `OpenAICompatibleProvider`, `OllamaProvider`. No redirects followed, 60 s timeout, errors carry the status and a trimmed provider message with the key removed. **Documentation read on 2026-10-27** (see "Provider documentation" below)
- [x] **Privacy guard** (`app/ai/privacy.py`): code-owned `PromptTemplate`s whose `{{fields}}` must be on `ALLOWED_FIELDS` (curriculum text only); detection of emails, phones, SA ID numbers, student/staff/ID numbers, long digit runs, IPv4, title plus name, and the names of this installation's users; **refusal by default** (counts and kinds, never the text), redaction as an admin choice with a second scan; the assembled prompt is scanned again; a sealed `GuardedRequest` is the only thing adapters accept. A static test checks that only the gateway builds a provider and that adapter signatures take only `GuardedRequest`
- [x] **Encrypted keys** (ADR 041, `app/core/secrets.py`): Fernet from `cryptography` (added to `pyproject.toml`; it was already installed through `joserfc`), `SECRETS_ENCRYPTION_KEYS` (newest first) plus a key derived from `SECRET_KEY` kept for reading, stored as `ocmp1:<key id>:<token>`; `new-encryption-key` and `rotate-secrets` commands (tested, in `docs/admin/basics.md`); keys are write-only (status only, no last four), in `__audit_exclude__`, scrubbed from provider errors; `hide_input_in_errors` on the settings so a bad key is not echoed. Rotation steps in the admin guide and `.env.example`
- [x] **Settings and budgets** (models `AISettings`, `AIProviderConfig`, migration `0019` which also adds the run type `connection_test`; `app/services/ai_settings.py`, `ai_budget.py`): provider, local-only mode (blocks any provider not marked local, in the gateway and when saving), the outside-South-Africa acknowledgement (who, when; stops covering the provider when its address or location changes; withdrawn when AI is turned off), monthly cost/token/call limits, calls per run, tokens per answer, usage this month from the run and call tables, a clear refusal with the reset date, a blocked state on the screen. A change is made in a savepoint and checked as a whole
- [x] **Gateway** (`app/services/ai_gateway.py`): checks, guard, budget, call, then an `ai_runs` row (or the caller's run) and an `ai_run_calls` row holding exactly what was sent; guard and budget refusals leave a run with counts only; logs hold ids, counts and timings only (tested by capturing the log output)
- [x] **API** (`/api/v1/ai/settings` GET and PATCH, `/ai/test-connection` POST; `settings.manage`; audited as `ai.settings_update` and `ai.connection_test`; the test is limited to five a minute per admin). `AIRefusedError` maps to 409 and `ProviderError` to 502 for later callers
- [x] **Screen** (`frontend/src/admin/AiSettingsPage.tsx`, `/admin/ai`, linked from Admin): status card with usage and the test button, provider choice with its fields, the ochre warning with its acknowledgement, privacy (local-only switch, refuse or redact), budget, a key field that is always empty, and loading, error, saved, refused, blocked and off states; strings under `admin.ai.*`
- [x] Docs: ADR 041 and 042 (in the index), `docs/admin/ai.md` (in the nav), configuration guide (new Secrets section; the unused `AI_*` settings removed), `.env.example`, backup guide (keep the keys with the backup), `docs/privacy/data-inventory.md` (AI processing rewritten; new tables, Redis counter, logs, outside transfer), CLAUDE.md convention, command reference. The Phase 0 variables `AI_ENABLED`, `AI_ANTHROPIC_API_KEY`, `AI_OPENAI_*`, `AI_OLLAMA_BASE_URL` and `AI_MONTHLY_BUDGET_CAP` were never read and are removed

**Provider documentation** (read with WebFetch on 2026-10-27; the adapters' docstrings and ADR 042 repeat this):
- **Anthropic: verified.** `platform.claude.com/docs/en/api/messages` (endpoint, `x-api-key`, `anthropic-version`, body), `.../get-started` (a real request and response with `content` blocks and `usage`), `.../api/errors` (error shape and statuses) and `.../models/overview` (current model ids `claude-fable-5-1`, `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5`; offered as suggestions, not hard-coded). The messages page was truncated before its response section; the response shape comes from the get-started page. `temperature` is sent only when the admin sets it, since current models were not checked for accepting it
- **Ollama: verified.** `github.com/ollama/ollama/blob/main/docs/api.md` (`/api/chat`, `stream: false`, `format`, `options`, `message.content`, `prompt_eval_count`, `eval_count`). The page gives no error body and does not document `num_predict` for chat, so errors are reported by status and no output limit is sent
- **OpenAI-compatible: partly verified, not stubbed.** OpenAI's own API reference was unreachable (HTTP 403 at `platform.openai.com`, 404 at the `developers.openai.com` reference addresses tried; the guide page that did load covers only the Responses API). The chat completions request and response were read in Microsoft's Azure OpenAI v1 REST reference (`learn.microsoft.com/en-us/rest/api/microsoft-foundry/azureopenai/chat`: `POST {endpoint}/openai/v1/chat/completions`, `max_completion_tokens`, `choices`, `usage.prompt_tokens` and `completion_tokens`, `api-key` or `authorization` header) and Ollama's OpenAI compatibility page (`docs.ollama.com/api/openai-compatibility`: `/v1/chat/completions`, `max_tokens`, `temperature`). The adapter is built on those two sources and says so in its docstring, the admin guide and the screen; it should be re-read against OpenAI's page when reachable (Decisions to review)

**Verification**:
- Backend: ruff check, ruff format --check and mypy (120 files) pass; the **whole pytest suite passed** against the test database (container `ocmp-test-db`, port 55432): 1207 passed in 16.5 minutes, 96% coverage. One more test (turning AI off withdraws the acknowledgement) and a change to how the settings row is created were made while that run was going, so the AI, secrets, CLI and config test files were run again afterwards (186 passed, 176 with coverage) with ruff clean; the whole suite was not run a second time. New: `test_secrets.py` (key format, rotation, missing key, tampering, derived fallback, a bad configured key not echoed), `test_ai_privacy.py` (44: every detector with positive and negative text, user names, redaction placeholders do not re-trigger, counts-only messages, field allow-list, seal, final scan), `test_ai_providers.py` (36: request and response of each adapter with `httpx.MockTransport`, key header, key scrubbed from errors, redirect not followed, unreachable provider, Null provider, address rules), `test_ai_settings_api.py` (45: 401/403, defaults, choosing providers, local-only, acknowledgement and its loss, fixed fields, write-only key in responses, in the database and in the audit log, unreadable key, budgets, test button states, rate limit, audit), `test_ai_gateway.py` (24: every refusal before sending, the stored run and call, logs without content or keys, provider errors recorded, run limits, every budget limit with its message, month boundaries, prices, local provider, static checks), two CLI tests. Module coverage: `app/ai/*` 91 to 100%, gateway 98%, settings service 96%, budget and secrets 100%. No test makes a real network call and no real key exists anywhere (placeholders only)
- Frontend under Node 24.22.1: lint and typecheck pass; **298 tests pass** (18 new in `admin/AiSettings.test.tsx`: the request built from the form, key sent only when typed, suggested address saved only when chosen, acknowledgement rules, off state, retry, warning and required tick, key write-only after saving, server reason shown, limit checks, empty limit means none, unreadable key, blocked reasons, test button states and results); run once with default workers as CI does (55 s)
- `mkdocs build --strict` passes
- Docker: all images rebuilt (`up -d --build --wait`); `migrate` applied `0019`. Playwright (Chromium), the **whole suite: 95 passed** with `--workers=1` (89 before + the new `e2e/ai-settings.spec.ts` in light and dark): off by default; the warning, the required tick and the server's local-only refusal; the blocked state (a cost limit without prices); the key is never in the page, after saving or after a reload; ready; a local provider on a closed port; limit validation; turning AI off withdraws the acknowledgement; a lecturer sees "No access". axe WCAG 2.2 AA on each of these states in both themes. The journey resets the settings in `afterEach`
- Census afterwards (read-only, through the ORM in the api container): AI settings are at their defaults (off, local-only on, refuse, default limits, no acknowledgement), the three provider rows exist with every field empty and no key, no AI runs or calls exist, the only live framework is the demo one, and the accounts are the operator's `e2e.admin@example.org`, `local.admin@example.org` and one other that were already there (plus earlier anonymised placeholders). The test lecturer is made and deleted by the suite. No accounts were created by this slice
- **Not verified here**: any real provider (no key was available and none was used: the adapters are checked against mocked transports built from the documentation, so a real Anthropic, OpenAI or Ollama call is untested); the OpenAI-compatible adapter against OpenAI's own page; "Test connection" in the browser (it would write an undeletable AI run; covered by API and unit tests); browsers other than Chromium; screen readers by hand; screenshots by eye; the CI run on GitHub (runs on push); the rotation procedure on a real server (the command is tested against the database, the full "edit `.env`, restart, rotate" sequence was not run); a restore on a server with a different `SECRET_KEY`; detection quality on real study-guide text (the patterns are tested on examples only)

**Not in this slice**: embeddings (1.15), any use of the layer by a feature (1.16 to 1.18), the evaluation page (1.19), per-user AI use limits, prices fetched from the providers, a last-four key hint, streaming, tool use, vLLM-specific options beyond the OpenAI-compatible adapter, other languages in the privacy patterns, a screen listing AI runs.

**Commit**: `feat: add the AI provider layer, privacy guard, encrypted keys, budgets and admin AI settings`
