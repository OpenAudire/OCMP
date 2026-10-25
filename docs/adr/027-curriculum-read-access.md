# ADR 027: Curriculum Read API and Who Sees What

## Status

Accepted (2026-10-25, Slice 1.2)

## Context

Slice 1.2 adds the first screens that read the curriculum: the builder's structure tree
and a programme and version switcher. Roles are scoped (ADR 012): a role applies at its
scope and everything below it, never above. Many people hold roles only at a module or a
single session (module coordinators, lecturers), and students may see published versions
only (brief section 7). A list endpoint cannot use `require_permission` with one scope,
and checking `has_permission` for every programme, version, module and session would
cost one lineage lookup per row.

## Decision

### Visibility rules
- `curriculum.view` at a scope shows every version there, drafts included;
  `curriculum.view_published` shows only **published** versions (not drafts or archived).
- A role at **programme level or above** (instance, faculty, programme) shows the whole
  version: all phases, modules, sessions and programme outcomes.
- A role at a **module** shows that module with all its sessions and outcomes, inside the
  phase that holds it. Other modules, empty phases and programme outcomes are hidden.
- A role at a **learning event** shows that session only. Its module appears as context
  (code and name, `context_only: true`); the module's details and outcomes are hidden.
- The programme's name and details are shown to anyone who sees any part of one of its
  versions, so the switcher can name what they work on.
- Soft-deleted rows, and programmes of a deleted faculty, are never shown.

### Implementation
- `app/services/curriculum_read.py` gathers the user's live role assignments once per
  request into permissions per scope (`CurriculumAccess`) and applies the rules above in
  bulk, with one query for module and session scopes. It mirrors `permissions_at`
  (`role_permissions` in the authorization service is now public so both use the same
  expansion of implied permissions).
- Endpoints (all `GET`, signed-in users only): `/programmes`, `/programmes/{id}`,
  `/curriculum-versions/{id}/structure`, `/curriculum-versions/{id}/outcomes`,
  `/modules/{id}`, `/learning-events/{id}`. The structure tree carries counts (objectives
  per item) and a `partial` flag; details and objectives are fetched when an item is
  selected, so the tree stays small for large programmes.
- Anything not visible is **404**, the same as something that does not exist, so the API
  does not reveal which programmes, versions or modules exist.

### Frontend
- `/curriculum` opens the version last opened in this browser (local storage, a
  convenience only) while it is still visible, otherwise the newest version of the first
  programme. `/curriculum/versions/{id}?item=module:{id}` names the version and selected
  item, so links and reloads keep the selection.
- The switcher is a menu in the header (in the page on phones): one labelled group per
  programme, the open version marked with `aria-current`.
- The structure tree is our own ARIA tree (single selection, roving tab stop, arrow keys,
  Home/End, Enter/Space), rendered flat with `aria-level`, `aria-posinset` and
  `aria-setsize`. Mantine's `Tree` was not used: it nests items, so each item's accessible
  name would include all its children, and it keeps the first item, not the selected one,
  in the tab order.

## Consequences

- Module and session scopes are rows of one version. When a year is copied forward
  (Slice 1.5), role assignments at module or session scope do not follow automatically;
  that slice must decide whether to copy them.
- A narrower role reveals the programme's name and details; this is intended (people
  need to know which programme their module belongs to) and matches the scope parent
  chain used for permissions.
- Editing (Slice 1.3) checks `curriculum.edit` per item with `require_permission`; these
  read rules only decide what is shown.
