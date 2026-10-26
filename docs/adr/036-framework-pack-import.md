# ADR 036: Framework Pack Import from the Screen, Pack Format Version 2 and Templates

## Status

Accepted (Slice 1.10). Builds on ADR 012 (permissions), ADR 014 (framework data model),
ADR 015 (tag lists), ADR 017 (audit log) and ADR 021 (pack import for the demo).

## Context

ADR 014 and ADR 021 left three things for the importer: the pack format had no crosswalks, no
tag lists and no references to other frameworks, and packs could only be loaded by code. The
brief (section 6) asks for import from a pack file with a preview, and for structure-only
templates for HPCSA core competencies, NQF level descriptors, a university's graduate
attributes and a MeSH subset, with no copyrighted framework text shipped.

## Decision

### Pack format version 2
- A new optional top-level `format_version` (integer). A pack without it is version 1, and
  every version 1 pack stays valid and imports as before. This installation reads up to 2; a
  higher number is refused with a message that says so.
- Version 2 adds, all optional:
  - `crosswalks`: each has a `from_version` (an earlier version of the same framework key that
    is already imported) and entries of type `equivalent`, `split`, `merged`, `removed` or
    `new` with `from_code` (in the earlier version) and `to_code` (in this pack). The pack is
    always the newer side, so a crosswalk is created while importing the new version.
  - `tag_lists`: key, name, kind, description, item types and values (label, optional code,
    description, order). A list that already exists only gets the values it lacks (matched by
    code, else label); nothing in an existing list is changed or removed.
  - Cross-references with `to_framework` (and optional `to_version`): the target is an item of
    another, already imported framework. Without a version the active version is used, else
    the newest; the preview says which one.
  - Cross-reference type `equivalent` (the model already had it).
- A pack that uses a version 2 section without `"format_version": 2` is refused with that
  message, so a typo cannot silently drop a section.
- `metadata.template: true` marks a blank template. A pack with it cannot be imported until the
  flag is removed, so placeholders cannot become a framework by accident.
- The schema file (`packs/schema/framework-pack.schema.json`) is the published description;
  the importer (Pydantic models in `app/services/packs.py`) is the authority, and a test keeps
  the schema's enumerations in step with the models.

### Validation in two stages, all problems at once
- `check_pack` needs no database and returns every problem found (up to 50) with its location
  (`items[3].parent_code`) in plain words. `resolve_pack` then looks up what the pack refers to
  in the database: the version already imported, other frameworks and their items, earlier
  versions for crosswalks, existing scales and tag lists. Unresolved references are errors,
  never silently skipped. `parse_pack` (used by the demo loader and tests) raises one
  `InvalidRequestError` listing the problems.

### Import flow (API and screen)
- `POST /framework-packs/preview`: the request body is the JSON file (no multipart form).
  It is read in chunks and refused with 413 above `PACK_MAX_UPLOAD_MB` (default 10) before it is
  parsed; a pack with more than `PACK_MAX_ITEMS` (default 20 000) items is an error in the
  preview. Problems in the file are a normal 200 answer with `valid: false` and the list. A
  valid preview keeps the file in Redis for 30 minutes under a random token tied to the user
  and answers with the token, the metadata, counts, any notes and the first 200 items in tree
  order. Previews are limited to 20 a minute per user.
- `POST /framework-packs/import` takes the token and an `activate` flag. It checks the pack
  again against the database (a version imported meanwhile is refused), imports in one
  transaction and deletes the token. Without `activate` the version is a draft; with it the
  version becomes active and earlier versions are superseded.
- Both need `frameworks.manage` for the whole institution. A pack with tag lists also needs
  `taglists.manage`; without it the preview says so. The import is labelled `framework.import`
  in the audit log with the key and version as the reason.
- Items are added level by level with `add_all` (one flush per level) instead of one query per
  item, as ORM objects so the audit log still records each row. 20 000 items import in about
  20 seconds on a development machine (measured, including audit rows).
- The screen is `/import` ("Import and export" in the menu), for people with
  `frameworks.manage`: choose a file, read the check, then confirm. Others still see the
  placeholder page.
- The messages the server sends about the file (problems, notes) are in English and shown as
  they come, like other server messages; the screen's own text is translated.

### Templates
- `packs/templates/*.json` (and an identical copy in `backend/app/pack_templates/`, enforced by
  a test, because the backend image cannot see `packs/`) hold four blank templates:
  `hpcsa-core-competencies`, `nqf-level-descriptors`, `graduate-attributes` and `mesh-subset`.
  `GET /framework-packs/templates` lists them and `GET /framework-packs/templates/{name}`
  downloads one.
- They are structure only. Every item says it is a placeholder and carries
  `metadata.placeholder: true`. No competency text, descriptor text or MeSH term is included,
  because none could be verified or licensed:
  - The NQF has ten levels (SAQA material found by search; the SAQA site itself could not be
    opened from here), so the template has the ten level items, titled by number only.
  - The HPCSA document was not consulted, so the template makes no claim about its areas or
    their number: two generic areas of two competencies show the layout.
  - For MeSH, NLM's data terms page (checked 2026-10-26) asks for the credit "Courtesy of the
    U.S. National Library of Medicine", forbids implying NLM endorsement, and asks that
    redistributed data be kept current or marked as possibly out of date. The MeSH licence
    page itself could not be verified, so the template's licence note is a placeholder that
    repeats those points. The descriptor identifier field is `DescriptorUI` in the MeSH XML
    (NLM's XML page); the template keeps it as `metadata.mesh_ui`.

## Consequences

- Spreadsheet (Excel) import of frameworks is a later slice (1.26) and will reuse the same
  validation and import service.
- Only JSON is read. The brief also mentions YAML; adding it is a parser change.
- Importing does not edit existing frameworks: a changed framework is a new version with a
  crosswalk. Re-importing the same key and version is refused.
- The token holds the whole pack in Redis for up to 30 minutes; the size limit bounds that.
