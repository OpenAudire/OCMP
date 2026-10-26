# ADR 035: Minimal Assessments and the Credits and Notional Hours Check

## Status

Accepted (Slice 1.9). Builds on ADR 012 (permissions), ADR 017 (audit log), ADR 027 (who sees
what), ADR 028 (structure editing), ADR 029 (copying), ADR 030 (versions) and ADR 015 (tag lists).

## Context

The brief (sections 3 and 9) asks for a minimal assessment (phase 1; blueprints come in phase
3) whose items link to objectives, and for the South African credit check: one credit is 10
notional hours (configurable); a module's notional hours are the contact time of its sessions
plus the estimated self-study plus the assessment time; the declared credits are compared with
them and flagged beyond a tolerance (default 10%); a year view of credits (typically 120 a
year, configurable); credits per NQF level checked against the qualification type's rules.

## Decision

### Assessments
- Three tables, all `Audited` and changed through ORM objects: `assessments` (module, name,
  method, weight, timing, learner time in minutes, position, `based_on_id`), `assessment_items`
  (assessment, label, marks, position, `based_on_id`) and `assessment_item_objectives` (the
  objectives an item assesses). Assessments and items are soft-deleted; the links are removed.
- The **method** is a value of an active `assessment_method` tag list (`GET /assessment-methods`
  lists the choices). A method in use cannot be deleted (409), only made inactive, as for
  teaching formats.
- **Weight** is a percentage (0 to 100) of the module mark. The weights of a module should add
  up to 100; the module screen says so when they do not. It never blocks saving.
- **Timing** is free text ("Week 8", "End of semester"). **Time in the assessment** (minutes)
  is the learners' time in the assessment itself and counts as assessment time in the notional
  hours.
- An item may assess objectives of **its own module and of that module's sessions** (422
  otherwise). Programme outcomes are reached through the objectives' upward links, so an item
  is not linked to them directly. `GET /modules/{id}/assessable-objectives` lists the choices.
- Endpoints: `POST /modules/{id}/assessments`, `PATCH/DELETE /assessments/{id}`,
  `POST /assessments/{id}/items`, `PATCH/DELETE /assessment-items/{id}`. Item changes return
  the whole assessment. Audit labels `curriculum.assessment_*` and
  `curriculum.assessment_item_*`.
- Permission: `curriculum.edit` at the **module** (as for sessions): module coordinators and
  above; lecturers can read but not change. What the user cannot see is a 404, a non-draft
  version is a 409. Assessments appear only where the whole module is visible (module detail:
  `assessments`, `can_edit_assessments`, `hours`); a user who sees only one session does not
  see them.
- **Copy and copy forward**: copying a module or a phase copies its assessments, items and the
  links to the copied objectives; copy forward does the same and records `based_on_id` on every
  copied assessment and item. Deleting a module or a draft version deletes its assessments.
- **Version diff**: assessments are a fifth kind (matched by lineage, then by name within
  matched modules) with the fields name, method, weight, timing, time and number of items.
  Items and what they assess are not compared.
- The word "assessment" is a fixed word in this slice (not one of the renamable terms).

### Credits and notional hours (advice only)
- The figures are the `credits` section of the institution settings (`CreditPolicy`):
  `hours_per_credit` (10), `tolerance_percent` (10), `credits_per_year` (120) and
  `min_exit_level_credits` (off). Changed through `PATCH /institution/settings` like the other
  sections.
- **Per module**: planned hours = contact + self-study of the live sessions + time in the
  assessments; expected hours = credits x hours per credit; the difference is `(planned -
  expected) / expected`. Status `ok` within the tolerance (the edge is `ok`), `under` or `over`
  beyond it, `no_credits` when the module has none. A module with 0 credits is `over` once any
  time is planned.
- **Per year**: each phase of kind *year* is compared with the typical credits per year
  (exactly: more or fewer is flagged). Other kinds of phase, and modules outside any phase
  (longitudinal), are totalled but not compared.
- **Per NQF level**: credits are totalled per module NQF level (modules without a level are
  listed separately). Against the programme: the total differs from the programme's total
  credits; the total is below the qualification type's minimum; a module is above the
  programme's NQF exit level (programme field, else the qualification type's); and, when the
  institution sets `min_exit_level_credits`, too few credits sit at the exit level.
- `GET /curriculum-versions/{id}/credit-check` returns all of it for a version that the user
  sees in full (404 otherwise); the module detail carries the module's own check. The builder
  shows the check in words with an icon (ochre means "needs attention", never colour alone)
  and has a **Credits and hours** page (`/curriculum/versions/{id}/credits`).
- It is advice: nothing is refused or blocked because of it, and there is no AI.
- The qualification rules are those seeded in `qualification_types` and must be checked against
  the current CHE and HEQSF documents; the page says so.

## Consequences

- Assessment blueprints (phase 3) can build on the same tables. Items already link to
  objectives, which is what the blueprint matrix needs.
- The credit check reads sessions and assessments live, so it is always current and needs no
  stored results.
- Reordering assessments and items, programme-level year definitions beyond the phase kind,
  and a settings screen for the credit figures are left for later.
