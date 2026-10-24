# CLAUDE.md - Project Conventions for Claude Code

This file documents the conventions and patterns used in the OCMP project to ensure consistency across development sessions.

## Project Overview

**Open Curriculum Mapping Platform (OCMP)** - An open-source, self-hosted curriculum mapping platform for universities.

## Repository Structure

```
/backend        FastAPI app (Python 3.12)
/frontend       React app (TypeScript, Vite, Mantine)
/packs          Framework/taxonomy pack schema and templates
/deploy         Docker Compose, Caddyfile, deployment scripts
/docs           MkDocs site, ADRs, PROJECT_BRIEF.md, PROGRESS.md
/scripts        Dev helpers, seed data, eval harness
```

## Technology Stack

- **Backend**: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic
- **Database**: PostgreSQL 16 with pgvector
- **Background jobs**: Dramatiq with Redis
- **Frontend**: React 18, TypeScript, Vite, Mantine v7, TanStack Query, React Router
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
```

### Important

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
// Example component
export function ProgrammeCard({ programme }: { programme: Programme }) {
  const { t } = useTranslation();
  return (
    <Card>
      <Text>{programme.name}</Text>
      <Badge>{t('common.credits', { count: programme.credits })}</Badge>
    </Card>
  );
}
```

### API Design

- All routes under `/api/v1/`
- RESTful resource naming
- Pydantic schemas for request/response
- Protected routes take `CurrentUser` (or `CurrentAuth`) from `app/api/deps.py`; CSRF is enforced by middleware (ADR 009)
- Check permissions with `Depends(require_permission(Permission.X, scope=...))`; never only in the UI (ADR 012)
- Raise `AuthorizationError` / `InvalidRequestError` / `ConflictError` from services; they map to 403 / 422 / 409
- HTTP status codes: 200 OK, 201 Created, 204 No Content, 400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found, 422 Validation Error

### Database

- All models inherit `CoreModel` (`app/models/base.py`): UUID PK, `created_at`, `updated_at`, `created_by_id` (see ADR 008)
- Soft delete via `SoftDeleteMixin` where history matters
- Relationships use `lazy="raise"`; load related rows explicitly with `selectinload`
- Register every model in `app/models/__init__.py` so Alembic sees it
- Scope resolvers for programme, module and learning event live in `app/services/curriculum_scopes.py`
- Enumerations: `StrEnum` stored as VARCHAR + CHECK (`str_enum()` in `app/models/base.py`), not native Postgres enums
- Uniqueness on soft-deletable tables: partial unique index via `live_unique()` (`WHERE deleted_at IS NULL`)
- Framework model fields follow the pack format in `packs/schema/` (ADR 014)
- Data migrations are separate files and use table stubs (`sa.table`), never app models
- Institution settings are read through `app/services/institution_settings.py` (typed sections), never raw JSON

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
- Audit log for curriculum/framework/mapping changes

### Testing

- Backend: pytest with pytest-asyncio
- Frontend: Vitest with Testing Library
- E2E: Playwright
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
| Files | snake_case.py | PascalCase.tsx | - |
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
- Tests mock `../api/endpoints` with `vi.mock` and use the real i18n setup

## Documentation

- ADRs in `/docs/adr/` for major decisions
- Update `PROGRESS.md` after each slice
- API docs auto-generated from OpenAPI
- User docs in MkDocs format

## Phase 0 Checklist

- [x] Project scaffold
- [x] Docker Compose base
- [x] Backend core + health
- [x] Core database models
- [x] Authentication (local + OIDC)
- [x] Roles and permissions
- [x] Curriculum models
- [x] Framework models
- [ ] Demo dataset
- [ ] Documentation skeleton
