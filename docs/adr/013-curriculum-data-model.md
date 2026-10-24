# ADR 013: Curriculum Data Model

## Status

Accepted

## Context

The brief (sections 6 and 9) describes the curriculum as programme → curriculum version →
phase → module → learning event, with objectives at programme, module and event level
linked upward, plus South African qualification data (HEQSF qualification types, NQF
levels, SAQA IDs, CHE and professional council accreditation).

## Decision

### Structure
- `qualification_types`: editable configuration table, seeded by a data migration with the
  brief's HEQSF values. Every seeded row carries a note that it must be verified against
  the current HEQSF; institutions can edit or deactivate rows.
- `programmes`: faculty, code, name, qualification type, NQF exit level, SAQA ID, total
  credits, minimum duration (years, one decimal), status (planned, active, phasing out,
  discontinued), CHE accreditation status and dates, professional council name,
  accreditation status and dates.
- `curriculum_versions`: one per programme and academic year, status draft / published /
  archived, `based_on_id` for copying a year forward, `published_at`.
- `phases`: kind year / phase / block / longitudinal thread, ordered by `position`.
- `modules`: belong to a version and optionally a phase (none for longitudinal modules).
  Credits allow one decimal. Coordinators are users holding the module coordinator role at
  the module (ADR 012), not a column.
- `learning_events`: contact and self-study minutes, position, week, LMS reference. The
  teaching format column arrives with tag lists (Slice 0.11).
- `objectives`: level programme / module / learning event; domain knowledge / skill /
  attitude; detected verb and quality flags for the quality checker (phase 1); status
  draft / approved / retired. The taxonomy level column arrives with taxonomy scales
  (Slice 0.10).
- `objective_links`: upward links from a narrower to a broader objective.

### Choices
- **Programme outcomes belong to a curriculum version**, not to the programme, so they are
  versioned and copied forward with the rest of the curriculum. Every objective stores its
  `version_id` so a whole version's objectives can be queried and copied directly.
- **Enumerations are `VARCHAR` with `CHECK` constraints**, not native Postgres enums, so
  adding a value is a simple migration.
- **Integrity in the database where practical:** check constraints for ranges (NQF 1–10,
  non-negative credits and minutes, academic year) and for the objective owner matching its
  level; a composite foreign key keeps a module's phase in the module's version; unique
  codes and years use partial unique indexes that ignore soft-deleted rows.
- **Rules in the service** (`app/services/curriculum.py`): objectives take their level and
  version from their owner; links must stay within one version, point to a broader level,
  and a session objective may only link to its own module's outcomes (or to programme
  outcomes).
- **Deletion:** curriculum rows are soft-deleted. A hard delete of a version removes its
  contents (cascade); programmes with versions cannot be hard-deleted.
- **Authorization scopes:** programme → faculty, module → programme (through its version),
  learning event → module (`app/services/curriculum_scopes.py`). A programme role covers
  every version's modules and sessions. Soft-deleted items are not scopes.

## Consequences

- Curriculum CRUD endpoints and the tree editor are phase 1 work; this slice provides the
  schema, rules and scopes they build on. The demo dataset (Slice 0.18) uses these models.
- Publishing rules (a published version becomes read-only), copy-forward and version diff
  are phase 1 features.
- Scheduled sessions (date, venue, group, facilitators) are phase 2.
