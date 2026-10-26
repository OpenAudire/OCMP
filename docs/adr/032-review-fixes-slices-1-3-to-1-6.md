# ADR 032: Review Fixes to Slices 1.3 to 1.6

## Status

Accepted (2026-10-26, Slice 1.6a). Amends ADR 027 (read visibility), ADR 030 (returning a
published version to draft) and ADR 031 (objective status and upward links).

## Context

The owner reviewed the "Decisions to review" table for Slices 1.3 to 1.6, approved most
rows and changed four things. This ADR records those four decisions and how they were built.

## Decisions

### 1. Read-only sight of outcomes above a held scope (amends ADR 027)

Anyone who sees an item of a version (a session, a module or more) can read, for choosing
upward links:

- the version's **programme outcomes**, and
- for a session objective, the outcomes of **its own module**.

This is read-only and limited to the *text of outcomes* in the link pickers
(`GET /modules/{id}/outcome-link-options`, `GET /learning-events/{id}/objective-link-options`
and the same list when saving links). Nothing else above the held scope is opened: the
programme outcome list endpoint, the module details, other modules' outcomes and the
structure stay as ADR 027 says (404). Editing outcomes still needs `objectives.edit` at the
owning scope. The rule "links to outcomes the user cannot see are left alone when they save"
stays in the code, although with these options no link is hidden any more.

### 2. Draft, ready for review, and approval (amends ADR 031)

- `ObjectiveStatus` gains `ready_for_review` (migration `0014` widens the status CHECK
  constraint; the downgrade sets such objectives back to `draft`).
- Anyone with `objectives.edit` may set **draft** or **ready for review**.
- Setting **approved** or **retired**, and leaving them, needs the new permission
  **`objectives.approve`** at the owning scope. System roles: platform admin, curriculum
  office, programme director and module coordinator. Lecturers do not have it.
- A lecturer who changes the wording of an *approved* objective sends it back to
  *ready for review* (so wording cannot change after approval unseen); a *retired*
  objective's wording needs the permission.
- Enforced in the service (`curriculum_objectives.py`) and the API answers 403. Read
  responses carry `can_approve_objectives` (module, session) and `can_approve_outcomes`
  (structure); the dialog offers only the statuses the user may set and locks the status of
  an approved or retired objective for people without the permission.
- No data migration: system roles are synced from `core/permissions.py` by
  `python -m app.cli sync-roles`, which the `migrate` service runs after every
  `alembic upgrade` (ADR 012). Custom roles are not changed; an administrator can add
  `objectives.approve` to them.

### 3. Returning a published version to draft (amends ADR 030)

- New permission **`curriculum.unpublish`**, held by curriculum office, programme director
  (the `_CURRICULUM_LEADERSHIP` set) and platform admin. The status endpoint still needs
  `curriculum.publish`; the published-to-draft change needs both.
- A written **reason** is required: `reason` in the request body, trimmed, 1 to 500
  characters (422 otherwise). It is recorded in the audit log as the `reason` of the
  `curriculum.version_unpublish` operation. Other transitions are unchanged and need no
  reason.
- The structure response carries `can_unpublish`; the confirm dialog asks for the reason.
- The reason is free text typed by a staff member. Do not put personal data in it.

### 4. Accepted mappings need a re-check after the wording changes

- `mapping_links.needs_recheck` (boolean, default false; migration `0014`) is set on an
  objective's **accepted** links when its text changes (`flag_for_recheck`, through ORM
  objects so the audit log records it). The links stay accepted; reviewers and decisions are
  untouched. Suggested, rejected and second-review links are not flagged: they are still
  waiting for a decision.
- It is cleared by `confirm_recheck` (needs `mapping.review` at the objective's scope; audit
  label `mapping.recheck_confirm`, with an optional reason) and by `reopen_link`.
  Copy forward keeps the flag with the copied link. A single-item copy does not copy
  mappings at all (ADR 029).
- Read API: objectives in the module, session and programme outcome responses carry
  `mappings_to_recheck` (count of accepted links that need it), and the builder shows a
  "needs re-check" chip with an icon and words. There is no mapping screen or report yet.
  **Reports must show the flag** (a "needs re-check" mark on accepted mappings, and a way
  to filter on it) when they are built; there is no HTTP endpoint to confirm a re-check
  yet, because mapping endpoints arrive with the mapping slices.

## Consequences

- Module coordinators now see the programme outcomes in the link picker even though they
  do not see the rest of the programme.
- The permission catalogue has two more entries; custom roles that should approve objectives
  or return versions to draft must be given them.
- Downgrading migration `0014` turns `ready_for_review` objectives back into drafts (the
  only data change, and only on a downgrade).
