# OCMP Development Progress

This file tracks progress through the development phases.

## Current Phase: Phase 0 - Foundations

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
**Status**: Pending

---

### Slice 0.16: Frontend Auth
**Status**: Pending

---

### Slice 0.17: First-Run Setup Wizard
**Status**: Pending

---

### Slice 0.18: Demo Dataset
**Status**: Pending

---

### Slice 0.19: Documentation Skeleton
**Status**: Pending

---

### Slice 0.20: CLAUDE.md & PROGRESS.md Finalization
**Status**: Pending

---

## Phase 0 Definition of Done

- [ ] Fresh Linux server with Docker can be set up by following install guide
- [ ] CI is green
- [ ] Demo data loads with one command
- [x] Role permissions covered by tests
