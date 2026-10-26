# CLAUDE.md - Project Conventions for Claude Code

This file documents the conventions and patterns used in this project to ensure consistency across development sessions.

## Project Overview

**Curriculum in Context** - An open-source, self-hosted curriculum mapping platform for universities.
People see only the product name (no acronym); technical identifiers stay `ocmp`
(repository, package, CLI, images, compose project, `OCMP_*` variables) (ADR 025).

## Repository Structure

```
/backend        FastAPI app (Python 3.12)
/frontend       React app (TypeScript, Vite, Mantine)
/packs          Framework/taxonomy pack schema and demo pack
/deploy         Docker Compose, Caddyfile, backup/restore scripts, .env.example
/docs           MkDocs site (operations/, admin/), ADRs, PROJECT_BRIEF.md, PROGRESS.md
/scripts        Dev helpers, eval harness (stub until Phase 1)
mkdocs.yml      Documentation site configuration
```

Backend (`backend/app/`):

```
main.py         App factory, middleware, lifespan
cli.py          `python -m app.cli` commands (setup-token, create-admin, load-demo, ...)
worker.py       Dramatiq entry point; imports every module in jobs/
api/            deps.py (auth, permissions, settings deps), health.py, v1/ routers
core/           config, logging, database, redis, broker, security, csrf, proxy,
                permissions (catalogue + system roles), profiles (terms, features)
models/         SQLAlchemy models; base.py has CoreModel, mixins, Audited, str_enum, live_unique
schemas/        Shared Pydantic schemas (router-only schemas may live in the router)
services/       Business logic; service errors live in services/authorization.py
jobs/           Dramatiq actors
demo/           Demo dataset loader and data
ai/, connectors/  Placeholders for Phase 1 (AI) and Phase 2 (LMS connectors)
```

Frontend (`frontend/src/`): one folder per feature (`auth/`, `account/`, `setup/`,
`layout/`, `routes/`, `session/`, `institution/`, `curriculum/`, `admin/`, `api/`, `pages/`), plus `theme/` (tokens,
Mantine theme, fonts) and `ui/` (shared `Page` and state components); tests beside the code.
Playwright journeys live in `frontend/e2e/`.

## Technology Stack

- **Backend**: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic
- **Database**: PostgreSQL 16 with pgvector
- **Background jobs**: Dramatiq with Redis
- **Frontend**: React 19, TypeScript, Vite, Mantine v9, TanStack Query, React Router; Node.js LTS (24) for tooling
- **Auth**: Argon2id hashing, session cookies, OIDC
- **Deployment**: Docker Compose with Caddy

## Development Environment Setup

### Backend

```bash
cd backend

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows:
.venv\Scripts\activate
# Unix/macOS:
source .venv/bin/activate

# Install all dependencies (including dev)
pip install -e ".[dev]"

# Run linting
ruff check .
ruff format --check .

# Run type checking
mypy app

# Run tests (database tests skip unless TEST_DATABASE_URL is set)
pytest

# Disposable test database for the database tests
docker run -d --name ocmp-test-db -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test \
  -e POSTGRES_DB=ocmp_test -p 55432:5432 pgvector/pgvector:pg16
TEST_DATABASE_URL=postgresql+asyncpg://test:test@localhost:55432/ocmp_test pytest

# Load the fictional demo dataset (BSc Health Sciences (Demo))
python -m app.cli load-demo

# First-run setup token (while no institution exists)
python -m app.cli setup-token

# Create or promote a platform admin (password from OCMP_ADMIN_PASSWORD or prompt)
python -m app.cli create-admin --email admin@example.org --name "Admin"

# New migration after changing models (review the generated file)
alembic revision --autogenerate -m "add thing table"
```

### Full stack (Docker)

```bash
cd deploy
cp .env.example .env   # then set SECRET_KEY and POSTGRES_PASSWORD
docker compose up -d --build --wait
# https://localhost (self-signed via Caddy); migrations run in the one-shot `migrate` service
```

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Run linting
npm run lint

# Run type checking
npm run typecheck

# Run tests
npm run test

# End-to-end + axe checks against the Docker stack (frontend/e2e/README.md)
E2E_EMAIL=... E2E_PASSWORD=... npm run e2e

# Dev server (proxies the API) and production build
npm run dev
npm run build
```

### Documentation site

```bash
# From the repository root, in its own virtual environment
python -m venv .venv-docs
.venv-docs/Scripts/pip install -r docs/requirements.txt   # Unix: .venv-docs/bin/pip
.venv-docs/Scripts/mkdocs build --strict                  # as CI; serve to preview
```

### Important

- **CI runs exactly the local commands** (`ruff check .`, `ruff format --check .`, `mypy app`, `pytest`) after `pip install -e ".[dev]"`; all tool settings live in `pyproject.toml`. Never add flags in CI that local runs do not use
- **Always use the virtual environment** for backend work
- **Never install packages globally** - add them to `pyproject.toml`
- Line endings are normalized to LF via `.gitattributes`

## Code Conventions

### Python (Backend)

- Use `ruff` for linting and formatting
- Use `mypy` with strict mode
- Async functions for all database operations
- Pydantic v2 models for API schemas
- SQLAlchemy 2.x async style
- Type hints on all public functions

```python
# Example service function
async def get_programme(db: AsyncSession, programme_id: UUID) -> Programme | None:
    result = await db.execute(select(Programme).where(Programme.id == programme_id))
    return result.scalar_one_or_none()
```

### TypeScript (Frontend)

- Strict TypeScript mode
- React functional components only
- Use `useTranslation` for all UI text
- Use TanStack Query for API calls
- Use Mantine components

```typescript
// Example component: curriculum nouns come from terms.* so institution wording applies
export function ModuleCount({ count }: { count: number }) {
  const { t } = useTranslation();
  return <Badge>{`${count} ${t('terms.module', { count })}`}</Badge>;
}
```

### API Design

- All routes under `/api/v1/`
- RESTful resource naming
- Pydantic schemas for request/response
- Protected routes take `CurrentUser` (or `CurrentAuth`) from `app/api/deps.py`; CSRF is enforced by middleware (ADR 009)
- Check permissions with `Depends(require_permission(Permission.X, scope=...))`; never only in the UI (ADR 012)
- Raise `AuthorizationError` / `InvalidRequestError` / `ConflictError` from services; they map to 403 / 422 / 409
- HTTP status codes: 200 OK, 201 Created, 202 Accepted (queued work), 204 No Content, 400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found, 409 Conflict, 422 Validation Error, 429 Too Many Requests (`too_many_attempts()` in `app/api/deps.py`), 503 Not Ready
- Register new routers in `app/api/v1/__init__.py`
- New settings: add to `app/core/config.py`, `deploy/.env.example` and `docs/operations/configuration.md` together
- New CLI commands: `app/cli.py`, tested in `tests/test_cli.py`, listed in `docs/admin/basics.md`

### Database

- All models inherit `CoreModel` (`app/models/base.py`): UUID PK, `created_at`, `updated_at`, `created_by_id` (see ADR 008)
- Soft delete via `SoftDeleteMixin` where history matters
- Relationships use `lazy="raise"`; load related rows explicitly with `selectinload`
- Register every model in `app/models/__init__.py` so Alembic sees it
- Scope resolvers for programme, module and learning event live in `app/services/curriculum_scopes.py`; objectives are edited in `app/services/curriculum_objectives.py` (`objectives.edit` at `objective_scope`, ADR 031)
- Only draft versions are editable; publishing, copy forward and the version diff live in `app/services/curriculum_versions.py` and `curriculum_diff.py` (ADR 030); copy forward records `based_on_id` on every copied row
- Curriculum reads filter by what the user may see via `app/services/curriculum_read.py` (ADR 027); not visible = 404
- Structure changes go through `app/services/curriculum_edit.py`; endpoints resolve their scope with an async
  resolver that answers 404 for what the user cannot see, then check `curriculum.edit` (ADR 028)
- Reorder with the `move_*` functions there (positions renumbered per sibling group, via the ORM);
  copy items with children through `app/services/curriculum_copy.py` (ADR 029)
- Drag and drop always has a keyboard and single-pointer alternative (Move up / Move down buttons)
- Enumerations: `StrEnum` stored as VARCHAR + CHECK (`str_enum()` in `app/models/base.py`), not native Postgres enums
- Uniqueness on soft-deletable tables: partial unique index via `live_unique()` (`WHERE deleted_at IS NULL`)
- Framework model fields follow the pack format in `packs/schema/` (ADR 014); import packs with `app/services/packs.py`
- `packs/demo/demo-graduate-competencies.json` and `backend/app/demo/data/` copy must stay identical (tested)
- Data migrations are separate files and use table stubs (`sa.table`), never app models
- Objective quality checker (ADR 033): pure rules in `app/services/objective_quality.py`, wording lists per language in `app/services/objective_rules/<code>.json`, verbs per taxonomy level stay in `taxonomy_levels.verbs`; findings are advice, never block saving, and use no AI. A finding's texts are i18n keys `curriculum.quality.<code>.*`: add all three (name, message, suggestion) with a new rule
- Tag lists are managed with `taglists.manage` (instance) and items are tagged with `tagging.edit` at the item's scope (ADR 034); inheritance rules, the preview and tag reads live in `app/services/tagging.py`: module to sessions, objective to the objectives linked beneath it, every inherited tagging points to the direct tagging it came from, only direct tags are removed (delete inherited rows through the ORM so they are audited); a list or tag in use is made inactive, not deleted
- Framework packs (ADR 036): format in `packs/schema/` (version 2 adds crosswalks, tag lists and references to other frameworks; no `format_version` means 1); validate with `check_pack` (all problems, no database) then `resolve_pack`; the import screen goes through `app/api/v1/framework_packs.py` (preview with a Redis token, then confirm). Blank templates live in `packs/templates/` and an identical copy in `backend/app/pack_templates/` (tested); they are structure only, never official text
- Tag lists are institution-wide (`faculty_id` null, `taglists.manage` at the instance) or a faculty's own
  (`taglists.manage` at that faculty); a faculty list tags only items of its faculty (ADR 015, 034).
  A tag already set is passed on to newer items only by the explicit `pass-on` action (ADR 034)
- Institution settings are read through `app/services/institution_settings.py` (typed sections), never raw JSON
- Assessments (ADR 035): `app/services/assessments.py` (module scope, `curriculum.edit`; items assess objectives of the module and its sessions only); copy and copy forward carry them in `curriculum_copy.py` with `based_on_id`; the diff has an `assessment` kind
- Credits and notional hours (ADR 035): pure rules in `app/services/credit_check.py`, figures in `settings["credits"]` (`CreditPolicy`); findings are advice and never block saving; texts are i18n keys `curriculum.credits.*`

### Background jobs

- Dramatiq actors live in `app/jobs/`; each module imports `app.core.broker` first and is imported by `app/worker.py`
- Job bodies are async functions run with `asyncio.run`; open connections with `job_resources(settings)`
- Never log email addresses or tokens; log user ids

### Audit log

- New models that hold curriculum, framework, mapping, organisation or access data inherit `Audited` (ADR 017)
- Mark personal columns `__audit_exclude__` (recorded by name only) and noisy ones `__audit_ignore__`
- Change audited data through ORM objects, not bulk `update()`/`delete()` statements (those are not captured)
- Label meaningful operations with `audit_operation("area.action", actor_id=..., reason=...)`
- Identify SSO users by (issuer, subject) only; never link or match accounts by email (ADR 011)
- Record admin views of personal data with `record_event(..., action="view")` (POPIA)
- Direct SQL that bypasses the audit log (raw `INSERT`/`UPDATE`/`DELETE`, `psql`, bulk
  statements) is allowed only on local test data, never in app code or on a real install;
  tests and e2e journeys change data through ORM objects or the API
- Statuses that need approval (objectives: approved, retired) are enforced in the service
  with `objectives.approve`; returning a published version to draft needs
  `curriculum.unpublish` and a trimmed reason passed to `audit_operation(..., reason=...)`
- Mapping links whose objective wording changed carry `needs_recheck`; reports must show it

### Testing

- Backend: pytest with pytest-asyncio
- Frontend: Vitest with Testing Library
- E2E: Playwright in `frontend/e2e/` against the Docker stack, light and dark projects, axe
  WCAG checks on every screen and state (`expectNoAccessibilityViolations`); never sign in
  inside a test (rate limits): use the saved session from `auth.setup.ts`
- End-to-end journeys remove everything they create (modules, tag lists, imported frameworks,
  grants) in `afterEach`, and `e2e/cleanup.teardown.ts` deletes the test lecturer (ADR 037)
- Backend tests are flat files `tests/test_<area>.py`; database tests skip unless `TEST_DATABASE_URL` is set, and CI always sets it
- Factories: factory_boy for models (`tests/factories.py`)
- API tests use the `api_client` fixture (test DB session, fakeredis, test settings)
- Never patch `app.core.config.get_settings` in tests; override dependencies or pass `Settings` explicitly
- `enqueued_jobs` fixture records `.send()` calls instead of using the broker; `tests/fakes.py` has `FakeEmailSender`
- Service tests use `example.org` addresses (`email_validator` rejects the `.test` domain)
- OIDC tests use `tests/fake_idp.py` (`FakeIdP` served via `httpx.MockTransport`)
- Authorization tests use `system_roles` fixture and `tests/authz_helpers.py` (`grant`, `curriculum_scopes`)

## Naming Conventions

| Entity | Backend | Frontend | Database |
|--------|---------|----------|----------|
| Models | PascalCase | PascalCase | snake_case |
| Functions | snake_case | camelCase | - |
| Files | snake_case.py | PascalCase.tsx (components), camelCase.ts (other modules) | - |
| Routes | /kebab-case | - | - |

## Commit Conventions

Use Conventional Commits:

```
feat: add coverage report export to Excel
fix: correct credit calculation for longitudinal modules
docs: update install guide for OIDC setup
test: add permission tests for module coordinator role
refactor: extract mapping service from router
chore: update dependencies
```

## Security Rules

- Never commit secrets (use `.env.example` with placeholders)
- Never send personal data to AI providers (enforced in code)
- Any change that adds, moves or changes personal data (a column, Redis key, log field,
  outbound flow) updates `docs/privacy/data-inventory.md` in the same commit
- CodeQL fails CI on any error or warning; fix it, or dismiss a false positive in code
  with a justification
- Workflows: explicit minimal `permissions`; third-party actions pinned to a commit SHA
  with a `# vX.Y.Z` comment (GitHub's own actions may use version tags)
- Parameterized queries only (SQLAlchemy handles this)
- CSRF protection on all state-changing endpoints
- Rate limiting on auth endpoints

## i18n

- All UI text must use translation keys
- English is the default language
- Translation files in `/frontend/src/i18n/locales/`
- No hard-coded strings in components
- Curriculum nouns use `terms.*` keys (e.g. `t('terms.module', { count })`), so institution terminology overrides apply

### Frontend structure (ADR 019)

- API calls go through `src/api/endpoints.ts` (shared axios client); add query keys to `queryKeys`
- Current user and permissions: `useSession()`; institution settings and features: `useInstitution()`, `useFeature()`
- Navigation visibility rules live in `src/layout/navigation.ts`; they only shape the UI, the API enforces permissions
- Tests mock `../api/endpoints` with `vi.mock`; render with `renderAt()` from `src/test/renderApp.tsx` (real i18n)
- Errors: Mantine `Alert` (role alert); confirmations: `SuccessNotice` (role status)
- Pages wrap content in `Page` (`src/ui/Page.tsx`, the only h1); empty, loading and error
  states use `EmptyState`, `LoadingState`, `ErrorState` (`src/ui/States.tsx`)
- Colours come from the design tokens (`src/theme/tokens.ts`, `var(--cic-*)`, ADR 026), never
  raw values; teal = good/selected/primary, ochre = needs attention, and never colour alone
- Controls at least 44px tall; check new screens with axe in both themes
- Never hard-code server rules (e.g. password length): read them from the API

## Documentation

- ADRs in `/docs/adr/` for major decisions; add new ones to `docs/adr/index.md`
- Update `PROGRESS.md` after each slice
- API docs auto-generated from OpenAPI (`/api/docs`)
- MkDocs Material site (ADR 022): `mkdocs.yml` at the root, operator guides in
  `docs/operations/`, admin guides in `docs/admin/`; new pages go in `nav`
- Update the guides in the same slice as the behaviour they describe (settings, commands,
  deploy files); `mkdocs build --strict` must pass
- No Python tags in `mkdocs.yml` (the `check-yaml` hook rejects them)
- Backup scripts in `deploy/` are POSIX `sh`; local deploy changes go in
  `deploy/caddy/*.caddy` or `deploy/docker-compose.override.yml`, never in tracked files

## Releases

- Tag `vX.Y.Z` on `main`; `.github/workflows/release.yml` runs CI and pushes
  `ghcr.io/openaudire/ocmp-backend` and `ocmp-web`. Running it by hand is a build-only dry run
- Compose uses `OCMP_BACKEND_IMAGE` / `OCMP_WEB_IMAGE` (default: local build)
- GHCR packages take the repository's visibility only when first created: tag the first
  release after the repository is public, or set both packages to public afterwards
- Docs treat the repository as public; private copies get a short note only
- Dependabot opens weekly grouped update PRs; review them like any other change

## Working in Slices

- Re-read `docs/PROJECT_BRIEF.md`, this file and `docs/PROGRESS.md` at the start of a session
- Each slice ends with: checks passing (backend ruff, format, mypy, pytest with the test
  database; frontend lint, typecheck, test; `mkdocs build --strict`), an end-to-end check
  in Docker where behaviour changed, `PROGRESS.md` updated, docs and ADR updated, one
  Conventional Commit
- Record what was verified and what was not in `PROGRESS.md`; never claim an unrun check
- Check current official documentation before integrating an external API (Brightspace,
  AI providers, LTI); if it cannot be verified, stub it behind an interface and say so
- Ask before changing the technology stack (via ADR)

## Status

Phase 0 is complete apart from installing on a real Linux server with public DNS (see the
Phase 0 Definition of Done in `docs/PROGRESS.md`). Phase 1 (core mapping) is planned after
approval of Phase 0.
