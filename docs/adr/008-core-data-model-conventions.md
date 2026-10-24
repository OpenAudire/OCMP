# ADR 008: Core Data Model Conventions

## Status

Accepted

## Context

The brief requires UUID primary keys, `created_at`, `updated_at` and `created_by` on all
tables, soft delete where history matters, and a schema managed by Alembic. The backend is
fully async (SQLAlchemy 2.x with asyncpg), where implicit lazy loading raises errors at
runtime instead of quietly issuing queries.

## Decision

All models inherit from `app.models.base.CoreModel`, which provides:

- `id`: UUID, generated in Python (`uuid4`) with `gen_random_uuid()` as a server default
- `created_at`, `updated_at`: `timestamptz` set by the database (`now()`)
- `created_by_id`: nullable FK to `users.id`, `ON DELETE SET NULL` (system actions have no user)
- `eager_defaults=True`, so server-generated values come back via `RETURNING`

Rows whose history matters add `SoftDeleteMixin` (`deleted_at`, `soft_delete()`, `restore()`).

Further conventions:

- **Constraint naming convention** on `Base.metadata` so migration names are deterministic.
- **Relationships use `lazy="raise"`**: callers load related rows explicitly (`selectinload`).
- **Case-insensitive email uniqueness** via a unique index on `lower(email)` rather than the
  `citext` extension.
- **Organisational FKs use `ON DELETE RESTRICT`**: faculties and departments are soft-deleted,
  never cascaded away.
- **The `vector` extension is enabled in its own migration** ahead of any embedding tables.
- **Tests run against real PostgreSQL** (`TEST_DATABASE_URL`). Migrations are applied once per
  session and each test runs in a rolled-back transaction. A test fails if the models drift
  from the migrations (`alembic check`).

## Consequences

- Each new table gets the standard columns automatically; a model that skips `CoreModel`
  needs a stated reason.
- Forgetting to eager-load a relationship fails loudly in tests rather than in production.
- `updated_at` uses transaction time, so it does not change between statements in the
  same transaction.
- Database tests skip when `TEST_DATABASE_URL` is unset; CI always sets it.
