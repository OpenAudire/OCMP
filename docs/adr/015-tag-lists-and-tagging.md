# ADR 015: Tag Lists and Tagging

## Status

Accepted

## Context

The brief (sections 3 and 6) asks for configurable tag lists ("mapping lists"): teaching
and assessment methods, themes and threads, keywords, resources, EPAs and custom lists;
taggings of curriculum items that record an inheritance source; and a teaching format for
each learning event taken from a tag list.

## Decision

- `tag_lists`: key (`^[a-z0-9_-]+$`, unique among live lists), name, kind (teaching method,
  assessment method, theme, thread, keyword, resource, EPA, custom), description, which item
  types the list may tag, active flag. Instance-wide, managed with `taglists.manage`.
- `tag_values`: label and optional code (for import upserts), both unique within a list
  among live values; description, position, active flag. Lists and values are soft-deleted.
- `taggings`: one row per tag on one item, with **one foreign-key column per taggable type**
  (programme, module, learning event, objective) and a check that exactly one is set. This
  replaces the brief's generic "entity type, entity id" with real referential integrity and
  cascades; a new taggable type (e.g. assessments) is one new column.
- `inherited_from_id` points to the tagging an inherited tag came from (`CASCADE`), so
  removing a source tag removes everything it passed on. An item can carry the same tag
  directly and by inheritance; uniqueness is per (tag, item, source).
- `learning_events.format_value_id`: the teaching format, a value from a teaching-method
  list (checked by the service; `SET NULL` if the value is removed). A column rather than a
  tagging because each session has exactly one format and contact-hour reports group by it.

Service rules (`app/services/tagging.py`): labels and codes unique per list; only active
values from active lists can be applied; a list applies only to its item types; deleted
items cannot be tagged; inherited tags must be the same tag as their source and are removed
at the source, not individually.

## Consequences

- Which tags flow down to which items, and the preview of affected items before saving,
  are built with the tagging UI in phase 1, on top of `inherited_from_id`.
- Default tag lists (e.g. common teaching formats) ship in packs and the demo dataset, not
  migrations.
