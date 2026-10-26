# ADR 028: Curriculum Structure Editing

## Status

Accepted (2026-10-25, Slice 1.3)

## Context

Slice 1.3 lets people add, change and delete phases, modules and learning events in the
curriculum builder. Roles are scoped (ADR 012) and the read API already decides what
each person sees (ADR 027). The brief gives programme directors the programme's
structure and module coordinators their modules and learning events (section 4).
Publishing rules (a published version becomes read-only) are Slice 1.5.

## Decision

### Permissions: the narrowest scope that owns the change
Every endpoint checks `curriculum.edit` with `require_permission`, at:

| Change | Scope checked |
|---|---|
| Add, change or delete a phase; add a module | Programme of the version |
| Delete a module; move a module to another phase | Programme of the version |
| Change a module's other fields; add a session to it; delete one of its sessions | Module |
| Change a session | Learning event |

Deleting or moving a module changes the programme's structure, so a module coordinator
may maintain their module and its sessions but not remove it or move it.

`require_permission` now takes an async scope resolver `(request, db, user)`. The
curriculum resolvers load the target, answer **404** when it does not exist or the user
cannot see it (the read rules of ADR 027, so the API still does not reveal what exists),
and keep the loaded rows on `request.state` for the endpoint. A visible target the user
may not change is **403**.

The structure response carries `can_edit` flags for the version (phases and modules),
each module and each session, computed in bulk from the same permissions. The UI shows
its buttons from these flags only; the API checks every change.

### Rules in the service (`app/services/curriculum_edit.py`)
- Only draft versions can be edited; published, archived and deleted versions are
  read-only: **409** (ADR 030 replaced the temporary rule that let published versions be
  edited until Slice 1.5).
- A module's phase must be a live phase of the same version, or none (longitudinal).
- Module codes are unique among a version's live modules, compared without case: **409**.
- New items go to the end of their parent; reordering is Slice 1.4.
- The session's teaching format must come from an active teaching-method list. Saving
  an unchanged format is allowed even if that value has since been retired.
- `GET /teaching-formats` lists the values to choose from.

### Deleting
- Soft delete only. A phase that still holds modules cannot be deleted (**409**); the
  user moves or deletes its modules first.
- Deleting a module also soft-deletes its sessions and the objectives of the module and
  its sessions; deleting a session soft-deletes its objectives. All rows get the same
  `deleted_at`, so a later restore can bring back exactly what went together.
- Links, mappings and taggings of those rows are kept; reads already ignore deleted rows.
- Role assignments at a deleted module or session are kept and grant nothing.

### Audit
All changes go through ORM objects and are labelled with `audit_operation`
(`curriculum.phase_create`, `curriculum.module_update`, `curriculum.module_delete`,
`curriculum.learning_event_create` and so on), attributed to the signed-in user.

### Frontend
- The details panel of the selected item shows its Add, Edit and Delete buttons (the
  mockup's single "+ Add learning event" button under the tree became per-item buttons,
  so every action sits next to the item it changes).
- Each change opens a Mantine `Modal` with a form; focus moves into the dialog and back
  to the button on Cancel or Escape. After adding or deleting, the new item (or the
  deleted item's parent) is selected and opened in the tree, and a confirmation
  (`SuccessNotice`, `role="status"`) receives focus because the button that opened the
  dialog is gone. After a change to the same item, focus returns to its Edit button.
- Delete dialogs say what goes with the item (sessions and objectives, by count).
- People who may add modules see the builder for an empty version instead of the empty
  state, so they can start adding.

## Consequences

- Slice 1.5 makes published versions read-only by changing `EDITABLE_STATUSES`; the UI
  follows through the `can_edit` flags.
- A restore screen (and the audit history per item) can build on the shared
  `deleted_at` of rows deleted together.
- Endpoints for later curriculum features (objectives, tags, mapping) can reuse the
  scope resolvers and the visibility-then-permission pattern.
