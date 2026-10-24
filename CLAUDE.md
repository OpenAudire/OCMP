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

# Run tests
pytest
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
- HTTP status codes: 200 OK, 201 Created, 204 No Content, 400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found, 422 Validation Error

### Database

- UUID primary keys
- `created_at`, `updated_at` on all tables
- Soft delete where history matters
- Audit log for curriculum/framework/mapping changes

### Testing

- Backend: pytest with pytest-asyncio
- Frontend: Vitest with Testing Library
- E2E: Playwright
- Factories: factory_boy for models

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

## Documentation

- ADRs in `/docs/adr/` for major decisions
- Update `PROGRESS.md` after each slice
- API docs auto-generated from OpenAPI
- User docs in MkDocs format

## Phase 0 Checklist

- [x] Project scaffold
- [ ] Docker Compose base
- [ ] Backend core + health
- [ ] Core database models
- [ ] Authentication (local + OIDC)
- [ ] Roles and permissions
- [ ] Curriculum models
- [ ] Framework models
- [ ] Demo dataset
- [ ] Documentation skeleton
