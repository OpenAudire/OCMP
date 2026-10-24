# ADR 017: Audit Log

## Status

Accepted

## Context

The brief requires that every change to curriculum, framework or mapping data writes an
audit entry (entity, action, before, after, actor, timestamp) (section 6), and under POPIA
(section 9): configurable retention for audit logs, an access log for personal data views
by admins, and audit-safe anonymisation of authorship when a user is deleted.

## Decision

### Capture
- Models marked `Audited` (curriculum, framework, tagging, mapping, organisation, roles,
  users; not AI run logs or the audit log itself) are recorded **automatically** by a
  SQLAlchemy `after_flush` hook: `create` (full row), `update` (changed fields only),
  `soft_delete`, `restore`, `delete` (full row). Automatic capture means a new service
  cannot forget to audit.
- Entries are inserted on the flush's connection, in the same transaction as the change,
  so they commit or roll back with it.
- `__audit_exclude__` columns are never written; a change to them is recorded by field name
  only (`context.unrecorded_fields`). Users exclude email, name and password hash, so a
  password change is visible without the hash. `__audit_ignore__` columns are not audited
  (users' and SSO identities' last sign-in time). `updated_at` is never recorded.
- **Not captured:** bulk `UPDATE`/`DELETE` statements and rows removed by database
  cascades. Services that change audited data use ORM objects (`activate_framework` was
  changed accordingly).

### Actor and operations
- The actor is a context variable set when a request authenticates; changes without an
  actor (commands, jobs, migrations) are `system`. A middleware gives each request a clean
  actor context.
- `audit_operation(name, actor_id=..., **details)` labels entries, e.g. reopening a rejected
  mapping is `{"operation": "mapping.reopen", "reason": ...}` by the reviewing user.
- `record_event` records non-change events. Admin views of user records (`GET /users`,
  `GET /users/{id}`) are recorded as `view` with the user ids shown, not the search text.

### Integrity and retention
- `audit_log` has a strictly increasing `seq` for ordering and `occurred_at` from
  `clock_timestamp()` (the event time, not the transaction start).
- A trigger refuses `UPDATE` and `DELETE`, except: clearing `actor_id` when the acting user
  is deleted (`ON DELETE SET NULL`: anonymised authorship), and deletes in a transaction
  that has set `ocmp.allow_audit_purge`, which only the retention purge does.
- Retention: `AUDIT_LOG_RETENTION_DAYS` (default 0 = keep forever) and
  `python -m app.cli purge-audit-log`.
- Snapshots contain ids of other rows (e.g. a role assignment's user id), never their
  personal details.

### Reading
- `GET /api/v1/audit-log` with filters (entity type and id, actor, action, time range) and
  pagination, newest first. Needs the new `audit.view` permission (platform admins).

## Consequences

- Audit entries add one insert per flush that changes audited data.
- The trigger protects against accidental or application-level tampering, not against a
  database superuser.
- Scheduling of the purge commands (and of AI content retention) is left to the operator
  until periodic jobs are added.
