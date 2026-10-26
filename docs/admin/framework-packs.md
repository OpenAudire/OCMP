# Importing frameworks (framework packs)

A framework pack is a JSON file that holds one version of a framework: its items in a tree,
and optionally cross-references, crosswalks from earlier versions, tag lists and taxonomy
scales. The curriculum office imports packs on the **Import and export** page (`/import`).
The design is in [ADR 036](../adr/036-framework-pack-import.md) (see also
[ADR 014](../adr/014-framework-data-model.md)).

## Who can import

You need the `frameworks.manage` permission for the whole institution (curriculum office and
platform admin). A pack that contains tag lists also needs `taglists.manage`. Everyone else
sees a placeholder on that page.

## Importing a pack

1. Open **Import and export**. Under **Framework pack**, choose the `.json` file and select
   **Check file**.
2. If the file has problems, the page lists every one it finds with its place in the file (for
   example `items[3].parent_code`) and what is wrong. Problems are found in stages: mistakes in
   single fields first, then the checks across the tree, references and existing data, so
   fixing the first list can reveal more. Fix the file and check it again. Nothing has
   been saved.
3. If the file is fine, read the preview: the framework's name, key, version, publisher and
   licence note; how many items, cross-references, crosswalk entries, scales and tag lists will
   be added; notes (for example that other versions are already imported); and the first 200
   items in tree order.
4. Optionally tick **Make this the active version**. Earlier versions of the same framework
   then become superseded. Without it the version is imported as a draft.
5. Select **Import framework**. The page says what was added. The import is one step: either
   everything is added or nothing is. It is recorded in the change history as
   `framework.import`, with the key and version as the reason.

The checked file is kept on the server for 30 minutes so that confirming does not upload it
again; after that, check the file again. A version that is already imported is refused: a
changed framework is a new version (with a crosswalk), not an edit.

### Big files

The limits are settings (see [Configuration](../operations/configuration.md)):
`PACK_MAX_UPLOAD_MB` (default 10) and `PACK_MAX_ITEMS` (default 20 000). A bigger file is
refused before it is read, with a message. An import of 20 000 items took about 20 seconds on
a development computer; keep the page open while it runs.

## The pack format

The published description is `packs/schema/framework-pack.schema.json`. Packs without a
`format_version` are format 1 and stay valid. Crosswalks, tag lists and references to other
frameworks need `"format_version": 2`.

```json
{
  "format_version": 2,
  "metadata": {
    "key": "my-framework",
    "name": "My framework",
    "version": "2.0",
    "publisher": "Who publishes it",
    "licence": "What you may do with the text",
    "profile": "core"
  },
  "items": [
    { "code": "A", "title": "Area A", "order": 1 },
    { "code": "A.1", "title": "First competency", "parent_code": "A", "order": 1 }
  ],
  "cross_references": [
    { "from_code": "A.1", "to_code": "A", "type": "related" },
    { "from_code": "A.1", "to_code": "X.4", "type": "equivalent",
      "to_framework": "other-framework", "to_version": "1.0" }
  ],
  "crosswalks": [
    { "from_version": "1.0",
      "entries": [
        { "type": "equivalent", "from_code": "A.1", "to_code": "A.1" },
        { "type": "removed", "from_code": "A.2" },
        { "type": "new", "to_code": "A.3" }
      ] }
  ],
  "tag_lists": [
    { "key": "my-themes", "name": "Themes", "kind": "theme",
      "values": [ { "label": "Ethics", "code": "ETH" } ] }
  ]
}
```

Rules the importer checks (and lists all at once):

- Item codes are unique; every `parent_code` exists; there are no parent cycles; an item
  cannot be its own parent. Titles are not empty.
- Cross-reference codes exist. With `to_framework`, the target is an item of an already
  imported framework (`to_version`, if given, must be imported; otherwise the active version
  is used, else the newest). Import the other framework first.
- A crosswalk starts at an earlier version of this key that is already imported
  (`from_version`). Entry types: `equivalent`, `split`, `merged` (old and new item), `removed`
  (old item only), `new` (new item only). `to_code` is a code in this pack; `from_code` a code
  in the earlier version.
- Tag lists: unique keys, labels and codes within a list. A list that exists already only
  gets the tags it lacks; nothing existing is changed.
- Scales that exist already (same key) are reused unchanged.

Only JSON is read at present.

## Blank templates

The page offers four downloads. They contain **structure only**: placeholders you replace,
never official text.

| Template | Layout | What you must supply |
|---|---|---|
| `hpcsa-core-competencies` | Two competency areas with two competencies each (health profile) | Titles and text from the official council document for your profession, as many areas as it has; the licence or permission to reproduce it |
| `nqf-level-descriptors` | One item for each of the ten NQF levels | The level descriptor text from the current SAQA publication |
| `graduate-attributes` | Three attributes with two indicators each | Your institution's own wording |
| `mesh-subset` | Two broader descriptors with two narrower ones each | Descriptor names and identifiers (`metadata.mesh_ui`), and confirmation of the current NLM terms |

To use one: download it, replace every placeholder (and the `key`, `version`, `publisher` and
`licence` in the metadata), add items, then **remove `"template": true`** from the metadata.
A file that still has it is refused with that explanation.

!!! note "What was and was not checked"
    These templates were written without copying any framework text. The number of NQF levels
    (ten) comes from SAQA material found by search; the SAQA site itself could not be opened.
    The HPCSA document was not consulted, so the template claims nothing about its structure.
    For MeSH, NLM's data terms (checked 26 October 2026) ask for the credit "Courtesy of the
    U.S. National Library of Medicine", no suggestion that NLM endorses your product, and a
    statement that redistributed data may not be current; the MeSH licence page itself was not
    verified. Check the current terms before importing real MeSH data.

## Troubleshooting

| Message | What to do |
|---|---|
| The file is larger than N MB | Split the pack, or ask the administrator to raise `PACK_MAX_UPLOAD_MB` |
| The pack has N items; this installation accepts M | Split the pack or raise `PACK_MAX_ITEMS` |
| Framework 'x' is not imported yet | Import that framework first, then this pack |
| Version 'v' of 'key' is not imported | A crosswalk needs the earlier version in the system first |
| This is a blank template | Fill it in and remove `"template": true` |
| This preview has expired | Choose the file and check it again |
