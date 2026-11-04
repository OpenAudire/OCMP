# ADR 056: Exports of a Curriculum Version

## Status

Accepted (Slice 1.27). Builds on ADR 054 and 055 (the Excel imports, whose sheets and field definitions
the round-trip export writes), ADR 027 (what a user may see), ADR 051 (report exports) and ADR 050
(only accepted links count). Brief, Phase 1: "Full round-trip export of everything in the same
templates; matrix export (objectives x framework items); JSON export of a whole curriculum version."

## Decision

Three exports of one curriculum version (`services/curriculum_export.py`, router `api/v1/exports.py`).
All three contain **only what the person's roles show of the version** (a module coordinator gets their
part, and the file says it is partial). They need `reports.view` **and `curriculum.view`** at the
programme (or at a module for a narrower view): an external reviewer, who reads published evidence only,
may not export. A version the person cannot see is a 404. At most 20 exports a minute for each user.
File names are fixed and never contain user text. Nothing is stored.

### 1. Full round-trip workbook (whole version only)

One workbook in **the sheets of the import templates**: Phases, Modules, Sessions, Objectives (ADR 054),
Tag lists and Tag values, Mappings (ADR 055). Because it uses the same field definitions
(`import_fields.build_workbook`), **it imports back**, and a test checks that importing an export of a
version into the same version changes nothing (also for the curriculum, the tags and the mappings of the
real dev data).

The problem with a round trip is External IDs: items made on the screens have none. The export writes
such an item's **internal id** in the External ID column, and the import recognises it
(`curriculum_import.key_of`: an item answers to its External ID, or else to its internal id). So an
exported file updates the version it came from instead of duplicating it. The External ID column of an
exported row must not be changed: an import never renames an item's External ID, so a changed value is
read as a new item.

The Mappings sheet has an extra, informational **Status** column (an import ignores it). Rejected links
are not exported, retired objectives are. Faculty-owned tag lists are not exported (they cannot be
imported). Needs access to the **whole** version (403 for a partial view).

### 2. Matrix: objectives x framework items (Excel)

Rows are the visible objectives (level, module, session, wording), columns are the items of one chosen
framework in tree order (group columns in italics); a cell holds the **coverage score (1 to 5) of the
accepted link**, shaded by score, with the number of items covered at the end of each row and the number
of objectives covering each item at the bottom. Suggested, waiting and rejected links are not shown
(as in the coverage reports, ADR 050). Sheets: *About* (method, framework, version, time, partial notice),
*Matrix*, *Items* (code, title, level).

### 3. JSON of the version

One document (`schema` `ocmp.curriculum-version`, `schema_version` 1): the version, phases, modules,
sessions, objectives (with level, owner, status, broader objectives), assessments with items and the
objectives they assess, direct taggings with the tag values and lists they use, and all mapping links
with source, status, accept method and the re-check flag (rejected links included, with their status).
Items carry their internal id and their External ID. It is not an import format.

## What this does not do

* Export frameworks (they have their own pack format, ADR 036), users, roles or the audit log.
* Export several versions at once, or compare versions (the version diff has its own screen).
* Make the JSON importable; the Excel workbook is the round-trip format.

## Consequences

* Importing an export into the same version is a no-op, which makes the export a safe starting point for
  bulk editing in Excel.
* Any new field added to an import sheet must be written by the export too (the round-trip test fails
  otherwise).
