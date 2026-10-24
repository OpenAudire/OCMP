# ADR 014: Framework and Taxonomy Data Model

## Status

Accepted

## Context

The brief (section 6) asks for frameworks as data: versioned frameworks with item trees,
cross-references between items (gap G2: frameworks as a graph, used in coverage and
search), crosswalks between framework versions (gap G7: migrate links instead of remapping),
and taxonomy scales (Bloom revised, Miller, SOLO, Dreyfus, a combined Bloom + Miller scale)
with verb lists. Frameworks arrive as packs in the format defined in
`packs/schema/framework-pack.schema.json` (Slice 0.1).

## Decision

### Tables
- `taxonomy_scales` (key, name, description) and `taxonomy_levels` (position, name,
  description, verb list). Positions and names are unique within a scale; higher
  positions are more demanding. `objectives.taxonomy_level_id` points to a level
  (`SET NULL` if the scale is removed).
- `frameworks`: **one row per framework version**. Rows with the same `key` and different
  `version_label` are versions of one framework. Publisher, licence note, description, URL,
  profile (core / health / other) and status (draft / active / superseded / retired).
  Key format `^[a-z0-9-]+$` as in the pack schema; key + version unique among live rows.
- `framework_items`: code (unique per framework), title, description, `parent_id`, `depth`,
  `position`, and a JSON `metadata` column. A composite foreign key keeps a parent in the
  same framework; check constraints keep `depth = 0` exactly for top-level items and forbid
  an item being its own parent. Items are not soft-deleted: a framework version is fixed,
  and changes go into a new version with a crosswalk.
- `framework_cross_refs`: typed links (related, prerequisite, broader, narrower, equivalent)
  within a framework or across frameworks.
- `crosswalks` (from version → to version) and `crosswalk_entries` (equivalent, split,
  merged, removed, new). A check constraint ties which items are present to the entry
  type; the service also checks each item belongs to the right version.

### Pack alignment
Model fields follow the pack format so the importer is a direct mapping: `metadata.version`
→ `version_label`, `metadata.licence` → `licence_note`, item `order` → `position`,
`parent_code` → `parent_id`, item `metadata` → `metadata`, level `order` → `position`. A test
loads the shipped demo pack into the models.

### Rules in the service (`app/services/frameworks.py`)
- `add_item` derives depth from the parent and refuses parents from other frameworks and
  duplicate codes.
- `add_cross_ref` refuses self-links and duplicates.
- `add_crosswalk_entry` checks the items fit the entry type and come from the crosswalk's
  source and target versions.
- `activate_framework` makes a version active and marks the previously active versions of
  the same framework as superseded.

## Consequences

- Frameworks are instance-wide; managing them needs `frameworks.manage` (ADR 012).
- Phase 1 builds the pack importer, Excel import, framework browser and mapping on top of
  these tables. The pack schema does not yet describe crosswalks, tag lists or
  cross-framework references; it should be extended alongside the importer.
- No taxonomy scales are seeded by migration: they ship in packs (the demo pack has Bloom
  revised and Miller) and in the demo dataset (Slice 0.18).
