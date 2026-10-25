# OCMP Development Progress

This file tracks progress through the development phases.

## Current Phase: Phase 0 - Foundations (complete; awaiting a real-server install and approval)

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

**Commit**: `ci: add Dependabot, CodeQL and release images; add POPIA records`

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
- **Phase 2**: SAML (account service is protocol-independent), framework version migration, Brightspace connector and setup guide
- **SSO**: role mapping from claims, admin linking of existing local accounts, provider logout, multi-tenant Entra
- **POPIA**: per-user data export and deletion, email address changes (the inventory and notice template exist since Slice 0.21)
- **CI/CD**: first tagged release; GitHub Pages must be enabled for the docs workflow; code scanning upload once available (`CODE_SCANNING_ENABLED`); multi-architecture images
- **Deployment**: the embeddings image (optional profile, off by default) is built with the Phase 1 search features; move the docs from MkDocs Material (end of life 5 May 2027) to Zensical once it is stable

---

### CI fix and Node 22
**Status**: Complete

- [x] CI's backend lint job installed only ruff, mypy, pydantic and sqlalchemy and ran `mypy app --ignore-missing-imports`, so every other library became `Any` and strict mode failed with 45 errors on every commit. It now installs the project with dev extras and runs plain `mypy app` (settings from `pyproject.toml`), like local development (`cd8e46f`)
- [x] CI green on GitHub Actions for `cd8e46f`
- [x] CI and the frontend Docker image moved from Node 20 (end of life April 2026) to Node 22; the web image builds and serves on `node:22-alpine`

---

## Phase 0 Definition of Done

- [ ] Fresh Linux server with Docker can be set up by following install guide
- [x] CI is green (3e212d4)
- [x] Demo data loads with one command
- [x] Role permissions covered by tests
