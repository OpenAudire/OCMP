# ADR 057: Look-alike Warnings, the "Accepted by Import" Flag and Tag Columns

## Status

Accepted (Slice 1.27a). Builds on ADR 050 (coverage reports), 054 and 055 (the Excel imports) and 056
(the exports). Made after the owner's review of Slices 1.24a to 1.27.

## Context

Three gaps showed up when the imports and exports were reviewed together:

1. Items made on the screens have no External ID, so a file made elsewhere that describes the same
   items would silently make a second copy of each.
2. Mapping links imported as already decided are accepted with `accept_method = imported` and **no
   reviewer is recorded**, but the coverage reports flagged only links accepted in bulk. A reader could
   not tell which figures rest on links nobody in the system reviewed.
3. Themes, keywords and teaching methods could be applied to items only on the screens, even though the
   tag lists and tags can be imported.

## Decision

**Look-alike warnings.** After a valid check, every row that would **make** an item is compared with the
items of the version that no row of the file refers to. A warning (never a problem: the file can still be
applied) is given when:

* a **phase** has the same or a very similar name;
* a **module** has the same code (it cannot, if the module has an External ID: that is a problem already;
  a module without one is adopted by its code) or the same or a very similar name;
* a **session** has the same or a very similar title in the same module;
* an **objective** has the same or very similar wording, at the same level, under the same owner
  (programme outcomes among themselves).

"Same" means equal after lower-casing and removing everything but letters and digits; "very similar" is a
`difflib` ratio of at least 0.9 on that text (`SIMILAR_WORDING`). No embeddings and no AI: the check must work
with the embedding server off and must not depend on a model. Each warning names the sheet and row, says how
it matches, and gives the existing item's External ID (or, for an item made on the screens, its internal id,
which an import recognises, `key_of`) so the row can be changed to update that item. At most 50 are listed,
then a count.

**Imported links are flagged like bulk-accepted ones.** The coverage engine's `Link` has `imported` beside
`bulk`; every item reports `imported_links` and `only_imported`, the summary reports `imported_links`, and the
Excel and PDF reports have an "Accepted by import" column and say so in their notes. They are **counted**
(they are accepted links) and flagged, never hidden, exactly as ADR 050 requires for bulk links.

**Tag columns.** Modules, Sessions and Objectives get an optional **Tags** column (`import_fields.TAGS`):
entries separated by semicolons, each `list key: tag label`. The same definition makes the template and checks
the upload.

* The list and the tag must exist already (the tags import, ADR 055, makes them) and be active; the list
  must apply to that kind of item and be institution-wide or the version's faculty's. A bad entry is a problem
  naming the sheet, row and column, so nothing is applied.
* Tags are set **directly** (`tagging.tag_item`) and **not passed on**: inheritance is the person's choice on
  the screen, with its preview (ADR 034). Tags are **added, never removed**, like broader objectives; a blank
  cell changes nothing. A row whose item lacks a tag is an update with "Tags" among the changes.
* The round-trip export writes each item's direct tags in the same form (only active lists and tags, because
  an import could not set the others), so an export still imports back with no change (ADR 056). A label that
  contains a semicolon cannot be written in the cell.

## Alternatives considered

* **Matching rows to look-alikes automatically.** Rejected: a wrong guess would overwrite the wrong item. The
  person decides, by giving the row the External ID.
* **Embeddings for objective similarity.** Rejected here: they exist only when the local embedding server is on,
  and a warning that appears and disappears with a server would be confusing. Plain wording comparison is
  deterministic and explainable.
* **Clearing tags when the cell is blank.** Rejected: removing a direct tag also removes what it passed on;
  that should be a deliberate action on the screen.

## Consequences

* A large import compares each new row with the items under the same parent only, so the cost stays small.
* The warning is advice. An institution that really has two items with the same wording under one parent
  (an intentional repeat) just ignores it.
* Reports now have one more column and one more count; the API gained `imported_links` and `only_imported`.
