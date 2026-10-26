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
ADRs. Each can be changed; the last column says how much work that would be.

| Slice | Decision | Why | How hard to reverse |
|---|---|---|---|
| 1.3, replaced in 1.5 | ~~Published versions stay editable until Slice 1.5~~ Only draft versions are editable; published and archived are read-only (ADR 030). The demo now has a 2027 draft to edit | The publishing rules arrived with 1.5 | Easy: one constant (`EDITABLE_STATUSES`) |
| 1.3 | Phases, adding and deleting modules, and moving a module to another phase need `curriculum.edit` at the programme; a module's own fields and its sessions need it at the module; a session's fields at the session | Brief section 4: directors own the structure, coordinators their modules and sessions | Easy: scope per endpoint |
| 1.3 | Deleting is a soft delete that takes the children with it (module: its sessions and all their objectives; session: its objectives), with one shared timestamp | Keeps later reports and copy-forward from seeing orphaned objectives; a restore can bring back what went together | Medium: data already deleted this way would need a restore step |
| 1.3 | A phase holding modules cannot be deleted (the dialog explains why) | Avoids deleting many modules by accident | Easy |
| 1.3 | Module codes are unique per version ignoring upper/lower case (the database index is case-sensitive) | "hsc101" and "HSC101" in one version would confuse imports and reports | Easy |
| 1.3 | Write endpoints answer 404 for items the user cannot see and 403 for visible items they may not change | Same rule as the read API (ADR 027): the API does not reveal what exists | Easy |
| 1.3 | Add, Edit and Delete buttons sit in the details panel of the selected item, not one "+ Add learning event" button under the tree as in the mockup | Every action sits next to the item it changes, and the same pattern works for phases, modules and sessions | Easy (UI only) |
| 1.3 | New items go to the end of their parent; reordering waits for Slice 1.4 | Matches the plan | Easy |
| 1.3 | `require_permission` scope resolvers are now async and receive the database session and the user | Curriculum scopes need a lookup (version to programme) and a visibility check | Easy: no other endpoint used `scope=` yet |
| 1.3 | The request's database session now commits when the endpoint returns, before the response is sent (`Depends(..., scope="function")`) | Found by the new end-to-end journey: FastAPI ended `yield` dependencies after the response, so a read straight after a save could miss it, and a failed commit still answered 2xx | Easy: one line in `app/core/database.py` |
| 1.3 | Filled red (delete) buttons use the on-brand text colour, like filled brand buttons | White text on the dark theme's light red failed contrast (axe) | Easy |
| 1.4 | Moving phases and modules (order and copy) needs `curriculum.edit` at the programme; moving and copying sessions needs it at the module, so a lecturer cannot reorder or copy their own session | Same split as adding and deleting in 1.3 (ADR 028) | Easy: scope per endpoint |
| 1.4 | Reorder API takes the new index among siblings (`POST .../move {"position": n}`), not a full ordered list | One small request per move; a change elsewhere in the list does not make it fail | Easy |
| 1.4 | Drag and drop moves items only among their siblings; a module changes phase through Edit | Keeps the drop rules simple and matches the 1.3 phase-move permission | Easy (UI and one endpoint) |
| 1.4 | Native browser drag and drop, no library; keyboard and single-pointer path is Move up / Move down buttons in the details panel | The tree is our own ARIA tree; library keyboard sensors would compete with its arrow keys; WCAG 2.5.7 is met by the buttons | Easy: a library can replace the events, the API stays |
| 1.4 | A copy goes right after the original; sessions are copied only within their module | Avoids broken upward links (a session objective links to its own module's outcomes) | Easy |
| 1.4 | Copies take children, objectives (with status), upward links (remapped inside the copy) and tags; not framework mappings, role assignments or the LMS reference | Mappings are reviewed decisions about one objective and would double coverage; access and LMS links belong to the original | Medium: copies made so far would need their mappings added by hand |
| 1.4 | Copying a phase asks for a new code for each of its modules (no generated codes); the name defaults to "<name> (copy)" | Codes are meaningful and unique per version; the user chooses them | Easy (UI) |
| 1.4 | The long e2e journeys are marked `test.slow()` | With two more journeys in parallel, the 1.3 editing journey passed 30 s locally | Easy |
| 1.5 | A published version can be returned to draft (and an archived one published again) by people with `curriculum.publish`; archiving is one more step from published | Lets a mistake in a published year be corrected without copying the whole year; students stop seeing it meanwhile | Easy: the `TRANSITIONS` table |
| 1.5 | Publishing needs at least one module | An empty version should not reach students | Easy |
| 1.5 | Only drafts can be deleted (soft delete with contents, one timestamp); needs `curriculum.edit` | Published history must not vanish; drafts made by mistake can go, and the year becomes free | Easy |
| 1.5 | Per-item lineage: nullable `based_on_id` (self reference, `ON DELETE SET NULL`, indexed) on phases, modules, learning events and objectives, set by copy forward only (migration 0013) | The diff and later reports follow items across years even when renamed; additive, no data rewritten, clean downgrade | Medium: dropping the columns is simple, but the diff then falls back to matching by name and code |
| 1.5 | Copy forward also copies framework mappings with their review state, unlike a single-item copy (ADR 029); LMS references are not copied | A new year continues the same curriculum; a copy of one item would double coverage | Easy: one function (`_copy_mappings`); mappings already copied would need removing by hand |
| 1.5 | Copy forward keeps module codes and the order; the new year is chosen by the user (suggested: newest + 1), must be free | Codes are unique per version, so no clash | Easy |
| 1.5 | Copying roles needs `roles.assign` and every permission of each role (the assign rule); people without it get no names in the preview and copy the structure only | The preview shows holders' display names; the assign rule keeps escalation out | Easy |
| 1.5 | Version diff matches by lineage first, then by phase name, module code, session title and objective text; order, upward links, tags and mappings are not compared | Keeps the first diff readable; the rest can be added later | Easy |
| 1.5 | Only whole-visible versions of one programme can be compared; the UI offers "Compare versions" to people who see the whole version | Narrow roles see parts of versions only | Easy |
| 1.5 | Running `load-demo` on an install that has only the published demo version adds the 2027 draft instead of refusing; the draft is made by copy forward plus a few scripted changes | Existing trial installs get the new demo content without a reset | Easy |

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
| 1.11 | Framework library screen and tree browser with search and "where mapped" |
| 1.12 | Mapping workspace: manual linking, coverage 0-5 and depth with help text |
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
