# ADR 031: Objective Editing: Permissions, Upward Links and Taxonomy Levels

## Status

Accepted (Slice 1.6)

## Context

Objectives exist at three levels (programme outcomes, module outcomes, session
objectives; ADR 013) with a domain, a taxonomy level, a status and upward links. The
data model needed no change. Slice 1.6 adds the editor. The brief gives programme
directors the programme's outcomes, module coordinators their module and its sessions,
and lecturers the objectives of their own sessions (section 4). Only drafts are editable
(ADR 030), and reads show only what a person may see (ADR 027).

## Decision

### Permissions: `objectives.edit`, at the scope that owns the objective
The existing `objectives.edit` permission (not `curriculum.edit`) is checked with
`require_permission` at:

| Change | Scope checked |
|---|---|
| Add a programme outcome (`POST /curriculum-versions/{id}/outcomes`) | Programme |
| Add a module outcome (`POST /modules/{id}/outcomes`) | Module |
| Add a session objective (`POST /learning-events/{id}/objectives`) | Session |
| Change or delete an objective (`PATCH`, `DELETE /objectives/{id}`) | The scope of the objective's level (`objective_scope`) |

Roles held higher up count (a programme director edits everything below). A target the
user cannot see is **404**, a visible one they may not change is **403**, a version that
is not a draft is **409**. The read responses carry `can_edit_objectives` (module, session)
and `can_edit_outcomes` (version), already false for non-drafts; the UI follows them.

### Fields and rules (`app/services/curriculum_objectives.py`)
- Text is required (1 to 2000 characters). Domain (knowledge, skill, attitude) and taxonomy
  level are optional and can be cleared with `null`. Status is draft, approved or retired;
  any editor may set any status (there is no separate approval permission yet).
- The taxonomy level may come from any scale (`GET /taxonomy-scales` lists Bloom, Miller
  and so on with their levels); an unknown level is **422**.
- New objectives go to the end of their owner's list. Reordering objectives is not part of
  this slice.
- Deleting is a soft delete; links, mappings and taggings stay and reads ignore them.
- Changes go through ORM objects and are labelled `curriculum.objective_create`,
  `curriculum.objective_update` and `curriculum.objective_delete`; link changes made while
  saving an objective are audited under the same label.

### Upward links
- A link goes from a narrower to a broader objective of the same version. A module outcome
  links to programme outcomes; a session objective links to outcomes of **its own module**
  or to programme outcomes (`link_objectives`, unchanged).
- `parent_ids` in a create or update **replaces** the links to the objectives *on offer*
  to the user. What is on offer is what the user may see (ADR 027): programme outcomes need
  the whole version, module outcomes need the module itself
  (`GET /modules/{id}/outcome-link-options`, `GET /learning-events/{id}/objective-link-options`).
  Ids that are not on offer are **422**.
- Links to objectives the user cannot see are **left as they are** when they change the
  others. So a lecturer with only a session role can edit the wording and level of their
  objective without losing the links a coordinator set, but cannot choose links themselves.

### Frontend
- The details panel lists each level's objectives with **Add**, **Edit** and **Delete**
  buttons (per objective, named with a short excerpt of its wording so each is unique).
- One dialog for all levels: wording, domain, taxonomy level (grouped by scale), status and,
  below programme level, a checkbox group of the broader outcomes on offer. A note says when
  there are none, and how many links to unseen outcomes stay.
- Programme and module objectives are "outcomes" in the UI text; session objectives use
  `terms.objective`. Focus returns to the opening button after Cancel, Escape or a change;
  after a delete the confirmation takes focus.

## Consequences

- A lecturer whose only role is a session cannot link their objectives upward until
  coordinators or directors do so. Widening the options (showing the module's outcomes to
  its sessions' lecturers) is an easy follow-up if wanted: change `parent_options`.
- Slice 1.7's quality checker can read and write `detected_verb`, `quality_flags` and the
  suggested taxonomy level on the same objects; the editor does not touch those columns.
- Reordering, moving an objective to another session and bulk editing are later work.
