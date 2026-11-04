# ADR 054: Excel Template and Import of Curriculum Structure and Objectives

## Status

Accepted (Slice 1.25). Builds on ADR 028 (editing structure), ADR 030 (versions and copy forward),
ADR 031/032 (objectives), ADR 017 (audit log) and ADR 036 (the framework pack import, whose
preview-then-confirm pattern this follows). Brief, Phase 1 "Imports and exports": "Excel templates
with dropdowns and data validation ...; import preview with row-level errors, dry-run mode, upsert
by external ID, and an import job history." Excel templates "are generated from the same field
definitions used for validation, so they never drift" (brief, section on formats).

## Context

Institutions keep their curriculum in spreadsheets. Typing a hundred modules and a thousand
session objectives through the screens is not realistic, and importing them wrongly (duplicates,
half an import, unreviewed text) would be worse than not importing. This slice does the structure
and the objectives; tags, frameworks and mappings follow in Slice 1.26, the full export in 1.27.

## Decision

### One list of field definitions

`services/import_fields.py` defines four sheets (Phases, Modules, Sessions, Objectives) as lists of
`Field`s: heading, kind (text, long text, whole number, decimal, choice, reference), whether it is
required, limits, the dropdown list and the help text. The **template** (headings with help
comments, dropdowns, whole-number and decimal checks, an Instructions sheet and a Lists sheet) is
built from the definitions by `build_workbook`, and the **reading and checking** of an uploaded file
uses the same definitions. A test compares the template with the definitions. `build_workbook` also
takes rows, so the full export of Slice 1.27 writes the same sheets.

### Rows are matched by External ID

Phases, modules, sessions and objectives get a nullable `external_id` (migration 0028; unique per
version for phases, modules and objectives). Every row needs one: the code from the institution's own
system, or any unique text. A known External ID **updates** that item, a new one **creates** it.
**Copy forward keeps it** (not "duplicate a module" in the same version), so next year's file updates
next year's draft. An import **never deletes** anything, and never moves a session to another
module or changes the level or owner of an objective (it reports that as a problem).

A module that was made on the screens has no External ID: a row whose **Code** matches such a module
**adopts** it (the module is updated and takes the row's External ID). Phases, sessions and objectives have
no natural key and are matched by External ID only.

A column that is **absent** from a sheet is left alone; a column that is **present and blank**
clears that value (except *Broader objectives*, which only adds links and never removes any).

### Preview, dry run, apply

* `POST /curriculum-versions/{id}/import/preview` takes the workbook as the raw request body, reads
  and checks every row (all problems are listed with sheet, row and column, up to 500) and works
  out for each row whether it would be **created, updated or left unchanged** (and which fields
  change). **It writes nothing: the preview is the dry run.** A valid preview keeps the file in Redis for
  30 minutes under a random token tied to the user and the version (the same pattern as framework
  packs).
* `POST .../import/apply` with the token checks the file **again against the data as it is now** (if it
  now has problems, nothing is applied: 409) and then applies it **in one transaction** through the
  ordinary services (`curriculum_edit`, `curriculum_objectives`), so the rules of the screens hold
  (only draft versions, unique module codes, links only to broader objectives of the right place) and
  every change is in the audit log (operation `import.curriculum`). New objectives are **draft**; changing
  the text of an existing one follows the normal rules (it goes back to *ready for review* unless the
  person may approve). Embeddings are queued for the changed objectives.
* An import with any problem is **not applied at all** (no partial imports).
* Needs `curriculum.edit` and `objectives.edit` at the programme. A version the person cannot see
  is a 404; a published or archived version is 409.

### Import jobs

Each applied import writes an `ImportJob` row (audited): kind, version, status, and the counts by
sheet and action. **Never the file, its name or any cell.** The history screen is Slice 1.26.

### Limits and safety

The file is capped at `PACK_MAX_UPLOAD_MB`, 5 000 rows a sheet and 20 previews a minute. Cells are
cleaned of control characters and limited in length; text from the Lists sheet that looks like a
formula is written as text in the template. Reading uses openpyxl in read-only mode with
`data_only`; macros are never run and formulas are not evaluated.

## What this does not do

* Delete or archive anything, move items between owners, or change an objective's level.
* Import tags, frameworks, mappings, assessments or users (Slice 1.26 and later).
* Run in the background for very large files (a file is one request; the cap keeps it short).
* Translate the sheets (English headings; the templates are English for now).

## Consequences

* Four nullable columns, three partial unique indexes and one table (`import_jobs`).
* Anyone with programme edit rights can change a draft in bulk; the preview and the audit log are
  the safeguards, and the draft can be deleted or fixed by importing again.
