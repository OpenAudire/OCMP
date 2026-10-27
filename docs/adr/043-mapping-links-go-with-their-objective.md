# ADR 043: Mapping Links Go With Their Objective

## Status

Accepted (Slice 1.14b). Builds on ADR 017 (audit log), ADR 030 (versions and copy forward),
ADR 037 (deleting frameworks) and ADR 039 (mapping workspace). Settles the "orphaned links" remark
of Slice 1.12.

## Context

Deleting an objective (directly, or through its session, module or draft version) soft-deleted the
objective only. Its mapping links stayed live, so they still counted in the framework browser's
"where mapped" figures and blocked `DELETE /frameworks/{id}` with a 409. The end-to-end runs left
442 such links on the local stack. Hiding them at each reader would have left the rule to be
remembered by every later report.

## Decision

- **Soft delete for links.** `MappingLink` gets `SoftDeleteMixin` (`deleted_at`, migration `0021`)
  and stays `Audited`.
- **Deleted with the objective.** Every path that soft-deletes objectives (`delete_objective`,
  `delete_event`, `delete_module`, `delete_draft`) also soft-deletes their live links with the
  *same* `deleted_at`, through the ORM, inside the caller's `audit_operation`, so each link has its
  own audit entry under the same label. Deleting a phase needs it to be empty, so it has no
  objectives to take along.
- **Restore.** `restore_objective` clears the objective's `deleted_at` and restores the links whose
  `deleted_at` equals the objective's (the "deleted with" marker is the shared timestamp, so no new
  column). A link deleted at another time stays deleted. No endpoint restores objectives yet; the
  function is the one place that does and is tested. A link a person removes (`remove_link`) is
  still deleted for good, so nothing of that kind exists to be restored by mistake.
- **One pair, one live link.** The unique constraint on (objective, framework item) became a
  partial unique index over live rows (`live_unique`), so a deleted link never blocks a new one.
  Collision rule: on restore, a link whose pair has a live link again is left deleted (the newer
  link wins); nothing is merged.
- **One filter for every read.** `app/services/mapping_live.py::live_link()` is true for a link
  that is not deleted whose objective is not deleted. Every query on `MappingLink` uses it: the
  framework browser (where mapped, `mapped_count`), the workspace, the review queue and its counts,
  the objective re-check count, the framework delete check, the copy-forward preview and copy,
  and the lookups behind adding, flagging and listing links. Deleted links answer 404 on the link
  endpoints. Copy forward never copies deleted links. A rule in CLAUDE.md asks later reports,
  exports and imports to use it.
- **Clean-up of old data.** `python -m app.cli clean-orphan-links` (dry run by default, `--apply`
  to act) soft-deletes live links of deleted objectives through the ORM under the label
  `mapping.orphan_cleanup`, giving each the objective's `deleted_at`, so it behaves as if it had
  gone with the objective. A migration was rejected because it could not go through the ORM audit
  log (CLAUDE.md).

## Consequences

- The framework delete rule of ADR 037 now ignores deleted links and links of deleted objectives.
- Downgrading migration `0021` removes the soft-deleted link rows (they would collide with live
  ones in the old constraint).
- Reports (1.21) and exports must filter with `live_link()`; they do not exist yet.
