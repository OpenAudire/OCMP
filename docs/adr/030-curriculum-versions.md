# ADR 030: Curriculum Versions: Publishing, Copy Forward and Diff

## Status

Accepted (Slice 1.5)

## Context

The brief gives every programme one curriculum version per academic year with a status
(draft, published, archived) and `based_on` for copying a year forward, and asks to diff
two versions. Slice 1.3 (ADR 028) let published versions be edited temporarily. Owner
decisions (Slice 1.2): copy forward copies module and session role assignments by default,
listed in a preview where each can be unticked; expired assignments and deactivated or
deleted accounts are skipped and shown as skipped.

## Decision

### Status rules (`app/services/curriculum_versions.py`)
- Allowed changes: draft to published, published to draft, published to archived, archived
  to published (`TRANSITIONS`). Anything else is **409**. Publishing needs at least one
  live module. `published_at` is set on publishing and cleared when returning to draft.
- Only drafts are editable (`EDITABLE_STATUSES = {draft}`); the structure response carries
  `can_edit` false otherwise, so the UI hides the edit buttons. To correct a published
  version, return it to draft (students stop seeing it) or copy it forward.
- A draft can be deleted (soft delete with one timestamp, as for modules); other statuses
  cannot (409). The academic-year unique index ignores deleted rows, so the year frees up.
- `POST /curriculum-versions/{id}/status {"status": ...}` needs `curriculum.publish` at the
  programme (directors and curriculum office have it). The structure response carries
  `can_change_status` and `can_copy_forward`.

### Copy forward
- `GET .../copy-forward` previews counts, the suggested year (newest + 1), the years in
  use, and the role assignments; `POST` creates the draft (201) for a free year, with
  `role_assignment_ids` picked from the preview. Needs `curriculum.edit` at the programme;
  copying roles needs `roles.assign` and every permission of each role (the same rule as
  assigning), checked per assignment through `assign_role`. A user who cannot assign roles
  gets no assignment list (no names) and may not send ids (422).
- The copy reuses the ADR 029 machinery (`Copies` with a target version): modules, sessions,
  objectives of every level (programme outcomes too), upward links, taggings (inherited ones
  remapped). **Unlike a single-item copy it also copies framework mappings with their
  review state**, because the year continues the same curriculum; it does not copy LMS
  references. Module codes are kept (unique per version).
- Role assignments at module and session scope are copied with their expiry. Skipped, with
  the reason shown: ended assignments, deactivated or deleted accounts, roles the caller may
  not grant.
- The new draft has `based_on_id` set to the source version.

### Lineage
Phases, modules, sessions and objectives get a nullable `based_on_id` (self reference,
`ON DELETE SET NULL`, indexed; migration 0013, additive with a clean downgrade) set by copy
forward only. Single item copies (ADR 029) leave it empty.

### Diff (`app/services/curriculum_diff.py`)
`GET /curriculum-versions/{id}/diff?base=` for two whole-visible versions of one programme.
Items are matched by following `based_on_id` chains (either direction, so it works across
several years and for renamed items), then by natural key: phase name, module code,
session title within matched modules, objective text within matched owners. Reported:
added, removed and changed items with before and after values of name, kind, code, phase,
credits, NQF level, description, LMS reference, title, format, minutes, week, text, domain,
taxonomy level and status. Not compared: order, upward links, tags, framework links.

### Demo
The loader makes the published version, then copies it forward to next year's draft and
applies the changes in `next_year` of the demo data file (a renamed session, longer
contact time, an added session, a removed session, a reworded objective). Running
`load-demo` on an install with only the published version adds the draft; otherwise it
refuses as before.

## Consequences

- Returning a published version to draft is the way to correct it; the audit log records
  the status labels (`curriculum.version_publish` and so on).
- Lineage is per row, so a later feature (coverage against the last published version,
  Slice 1.28) can follow items across years without name matching.
- Soft-deleted rows keep their lineage pointers; only a hard delete clears them.
