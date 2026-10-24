# ADR 012: Roles and Scoped Permissions

## Status

Accepted

## Context

The brief (section 4) defines eight roles, each held at a scope (instance, faculty,
programme or module, or the user's own sessions). One person can hold several roles. The
One45 feature list adds custom roles. Permissions must be enforced in the API, and every
role/scope combination must be tested (ADR 006).

## Decision

### Permissions are code; roles are data
- `app/core/permissions.py` defines the `Permission` enum (what endpoints check) and the
  eight **system roles**. `curriculum.view` implies `curriculum.view_published`.
- Roles are rows in `roles`. System roles are created and kept up to date from code by
  `python -m app.cli sync-roles`, which the `migrate` service runs after migrations; they
  cannot be edited or deleted through the API. Platform admins can add **custom roles**
  made of any permissions, allowed scope types and an optional "must expire" flag.

| Role | Scope types | Summary |
|---|---|---|
| Platform admin | instance | everything |
| Curriculum office | instance, faculty | curriculum leadership + frameworks and tag lists |
| Programme director | programme | curriculum leadership (edit, publish, mapping, reports, evidence, assign roles) |
| Module coordinator | module | edit curriculum and objectives, tagging, mapping and review, AI runs, reports |
| Lecturer / facilitator | module, learning event | view curriculum, edit objectives |
| Mapper / reviewer | programme, module | view curriculum, mapping, first and second review |
| Student | instance, programme | view published curriculum |
| External reviewer | programme (end date required) | view published curriculum, reports, evidence |

"Own sessions" for lecturers is an assignment at learning-event scope. "Assigned items"
for mappers will come from review assignments in the mapping slices.

### Scopes
- `role_assignments` holds (user, role, scope type, scope id, optional `expires_at`). The
  scope id has no foreign key because its table depends on the type; the service checks it
  exists. The instance scope has no id (enforced by a check constraint).
- A role applies at its scope and everything inside it: instance > faculty > programme >
  module > learning event. It never applies upwards or to siblings.
- Each scope type registers a parent resolver (`register_scope`). Instance and faculty are
  registered now; programme, module and learning event register in Slice 0.9 when their
  tables exist. Until then, assignments at those types are refused as "not available yet".
- Expired assignments and inactive or deleted users grant nothing.

### Granting roles: no escalation
- To assign or remove a role at a scope, the actor needs `roles.assign` there **and** must
  hold every permission of that role there. A programme director can staff their own
  programme but cannot create a platform admin or a role with permissions they lack.
- The last active platform admin cannot be removed or deactivated, and users cannot
  deactivate themselves.
- `python -m app.cli create-admin` creates (or promotes) a platform admin. It is the
  bootstrap and recovery path until the first-run setup wizard (Slice 0.17).

### Enforcement in the API
- `require_permission(permission, scope=...)` is a FastAPI dependency that returns the
  signed-in user or answers `403`. `scope` derives the target scope from the request.
- Service errors map to HTTP centrally: `AuthorizationError` → 403,
  `InvalidRequestError` → 422, `ConflictError` → 409.
- Endpoints: `GET /permissions`, `GET/POST /roles`, `PATCH/DELETE /roles/{key}`,
  `GET/POST /role-assignments`, `DELETE /role-assignments/{id}`, `GET/POST /users`,
  `GET/PATCH /users/{id}`, `GET /users/{id}/role-assignments`, `GET /auth/me/roles`.

## Consequences

- New endpoints declare their permission and scope; tests for each new scoped resource
  should check at least one allowed and one refused role.
- Permission checks load the user's assignments and walk the scope chain on each check;
  fine at this size, cacheable per request later if needed.
- Changes to roles and assignments are logged now and will go to the audit log
  (Slice 0.13). Role mapping from SSO claims can build on this later.
