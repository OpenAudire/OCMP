# ADR 004: Database Migrations

## Status

Accepted

## Context

OCMP uses PostgreSQL with SQLAlchemy 2.x. We need a migration strategy that:
- Tracks schema changes reliably
- Supports both development and production workflows
- Allows rollback when needed
- Works with CI/CD pipelines

## Decision

Use **Alembic** with autogenerate, with manual review before committing.

### Workflow

1. Developer modifies SQLAlchemy models
2. Run `alembic revision --autogenerate -m "description"`
3. Review the generated migration file
4. Edit if needed (add data migrations, fix edge cases)
5. Run `alembic upgrade head` to test locally
6. Commit the migration with the model changes
7. CI runs migrations against test database

### Conventions

- One migration per logical change
- Migration messages use imperative mood: "add user table", "add index on email"
- Include both upgrade() and downgrade() functions
- Data migrations in separate files from schema migrations
- Never modify committed migrations; create new ones instead

## Rationale

1. **Autogenerate**: Catches most changes automatically, reducing manual work
2. **Manual review**: Catches issues autogenerate misses (data migrations, complex constraints)
3. **Alembic**: Standard tool for SQLAlchemy, well-documented, reliable

## Consequences

- `alembic/` directory in backend with version history
- All schema changes must go through migrations
- Production deployments run `alembic upgrade head` before starting
- Downgrade path maintained for rollback capability
