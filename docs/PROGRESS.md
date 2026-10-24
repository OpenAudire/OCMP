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
**Status**: Pending

---

### Slice 0.7: Auth: OIDC
**Status**: Pending

---

### Slice 0.8: Roles & Permissions
**Status**: Pending

---

### Slice 0.9: Curriculum Models
**Status**: Pending

---

### Slice 0.10: Framework Models
**Status**: Pending

---

### Slice 0.11: Tag Models
**Status**: Pending

---

### Slice 0.12: Mapping Models
**Status**: Pending

---

### Slice 0.13: Audit Log Service
**Status**: Pending

---

### Slice 0.14: Terminology & Profiles
**Status**: Pending

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
- [ ] Role permissions covered by tests
