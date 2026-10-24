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
**Status**: Pending (deferred - Docker Compose files exist, will verify when Docker available)

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
**Status**: Pending

---

### Slice 0.5: Auth: Local Accounts
**Status**: Pending

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
