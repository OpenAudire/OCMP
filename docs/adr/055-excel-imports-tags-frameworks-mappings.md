# ADR 055: Excel Imports of Tags, Frameworks and Mappings, and the Import History

## Status

Accepted (Slice 1.26). Builds on ADR 054 (the curriculum Excel import: field definitions, preview
that is the dry run, one transaction, import jobs), ADR 036 (framework packs), ADR 034 (tag lists),
ADR 039/040 (mapping links and their review). Brief, Phase 1 "Imports and exports": Excel templates
"for programmes, modules, events, objectives, tags, frameworks and mappings ... import preview with
row-level errors, dry-run mode, upsert by external ID, and an import job history."

## Decision

The shared parts of the curriculum import moved to `services/import_common.py` (reading a workbook
by sheet definitions, cleaning cells, the problem list and the plan). `import_fields.build_workbook`
takes the sheets it is to write, so each kind of import has its own template made from its own field
definitions (`import_fields_data.py`); a test compares each template with its definitions.

### Tags (`tag_import.py`, `taglists.manage`)

Sheets **Tag lists** (list key, name, kind, description, applies to) and **Tag values** (list key,
label, code, description). A list is matched by its **key**, a tag by its **label** within the list:
importing again updates. **Nothing is deleted or deactivated**; the kind of an existing list cannot
change; only institution-wide lists are imported (a faculty's own lists are managed on the screen);
a code must be unique in its list. Applying tags to items is not in this import (the curriculum
import sets teaching formats on sessions; other tags are applied on the screens or by a pack).

### Mappings (`mapping_import.py`, `mapping.edit` at the programme, draft versions)

Sheet **Mappings**: objective External ID (from the curriculum import), framework key (and optionally
version, otherwise the active one), item code, coverage 1 to 5 (the same bands as the reviewer's
screen), depth (blank means *matches*), reason. A new pair becomes a link with the source `import`:

* **By default it is only suggested**, in the importer's name, and goes to the review queue: the import
  never records a decision nobody made.
* Someone who may **review** mappings can tick "already reviewed elsewhere": the links are then accepted
  with the accept method `imported` (as the demo data's links are), **no reviewer is recorded**, and the
  count is kept in the import job.
* A pair that is already linked (in any state, rejected included) is **never changed**; it shows as
  "unchanged (already linked, accepted)".

### Frameworks (`framework_excel.py`, `frameworks.manage`)

Sheets **Framework** (one row) and **Items** (code, title, description, parent code). The workbook is
turned into a pack (format 1) and goes through `check_pack`, the same database checks, the same preview
and the same `POST /framework-packs/import` as a JSON pack, so nothing differs after the preview. A pack
problem is reported as sheet, row and column.

### Import history (`GET /import-jobs`)

Every applied import (curriculum, tags, mappings, framework) writes an `ImportJob` (counts only: never
the file, its name or a cell). The list shows your own jobs, or everyone's with `audit.view`, newest
first, with who, what, which version and the counts.

## What this does not do

* Delete, archive or move anything; apply tags to items; import assessments, users or programmes.
* Import a framework's cross-references, crosswalks or tag lists from Excel (use a pack file).
* Run big files in the background, or translate the sheets (English for now).

## Consequences

* A reviewer can bring in earlier accreditation decisions without re-reviewing them, and a person who
  cannot review can only suggest. Reports that flag bulk-accepted links should also flag `imported`
  ones (a later report slice); for now the accept method is stored and shown in the review screens.
* Three more templates, three more previews; the screen has one generic card for them all.
