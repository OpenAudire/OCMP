# ADR 038: Framework Library, Tree Browser and "Where Mapped"

## Status

Accepted (Slice 1.11). Builds on ADR 012 (permissions), ADR 014 (framework data model),
ADR 019 (frontend structure), ADR 027 (curriculum read access), ADR 036 (pack import) and
ADR 037 (deleting unused frameworks).

## Context

Frameworks could be imported (1.10) and deleted through the API (1.10a), but nobody could
read them. The brief asks for a library of frameworks, a tree browser with search and a view of
where each item is mapped (section 6). A framework can hold 20 000 items (the import limit), so
loading a whole tree into the page is not an option. Mapping links belong to objectives, and
people see only the curriculum their roles show (ADR 027): the "where mapped" view must not
reveal anything else, not even through counts. Mapping itself is Slice 1.12.

## Decision

### Who may read frameworks
- Reading needs `curriculum.view` or `frameworks.manage` at any scope, the same rule as the
  Frameworks entry in the navigation. Frameworks are shared by the institution, so there is no
  narrower scope. Someone without either gets 403 (the whole area is closed to them, as for
  other permission-guarded areas); a framework or item that does not exist (or was deleted, or
  belongs to another framework) is 404.
- Deleting stays `frameworks.manage` for the instance (ADR 037). The library shows a Delete
  button only when the API says `can_manage`, asks for confirmation and shows the server's
  refusal (409) in words. The permission is still checked by the API.

### Endpoints (`app/api/v1/frameworks.py`, `app/services/framework_browse.py`)
- `GET /frameworks`: every live version with item, top-level and level counts, publisher,
  licence note, status and `can_manage`.
- `GET /frameworks/{id}/items?parent_id=&offset=&limit=`: a window of the children of one
  parent (the top level without `parent_id`), in tree order (position, then code), at most 200
  at a time (default 100). Each item carries `child_count` and `mapped_count`. The window says
  its `offset` and the `total` number of siblings, so the screen can give each row its true
  `aria-posinset` and `aria-setsize`.
- `GET /frameworks/{id}/search?q=&offset=&limit=`: items whose code or title contains the text
  (case-insensitive, `%` and `_` are plain characters), exact code first, then codes that start
  with the text, then tree order, 50 a page, each with the path above it. It scans one
  framework's items, which is fast enough at 20 000 items (measured, see PROGRESS.md), so no
  extra index or extension (trigram, full text) was added. Meaning-based search is Slice 1.15.
- `GET /frameworks/{id}/items/{item_id}`: the item, its path with each ancestor's place among
  its siblings, and its own place, so the tree can open to it.
- `GET /frameworks/{id}/items/{item_id}/mappings`: the objectives linked to the item that the
  user may see (first 200, with the total).

### Lazy tree
The screen loads the top level and then one parent at a time when it is opened. Long lists of
siblings arrive as windows with "Show more" and "Show earlier" rows (they are tree items, so the
keyboard reaches them). Opening an item named in the address (`?item=`) or "Show in tree" after
a search loads only the siblings around each ancestor (about 50), not everything before it.
No virtualised list: windows keep the number of rows small, and people choose to load more.

### What "where mapped" shows
- A link is shown when it is not rejected and the user may see its objective by the rules of
  ADR 027, using the same functions as the curriculum screens (`visible_version`,
  `VersionView`): a version only if their roles show it (`curriculum.view` shows drafts too,
  `curriculum.view_published` only published ones), programme outcomes only to people who see
  the whole version, a module's outcomes to people who see the module, a session's objectives
  to people who see the session. Deleted objectives, modules, sessions, versions and programmes
  are left out.
- What the user cannot see is left out of lists **and counts** (`mapped_count` in the tree and
  search results, `total`), so a count never reveals hidden curriculum. A person who may read
  frameworks but sees no curriculum gets zero.
- Accepted, suggested and "waiting for a second review" links are shown, each with its status in
  words, coverage, depth and the "wording changed" and "reviewers disagree" flags that reports
  must show (ADR 032). Rejected links are not shown. No reviewer names are returned.
- Read only. Each row links to the objective's place in the curriculum
  (`/curriculum/versions/{id}?item=...`). Creating and changing links is Slice 1.12.

### Hidden in Phase 1
The mockup's coverage bars and "links" count (coverage reports, Slice 1.24), the version and
crosswalk panel with AI migration (Phase 2, plan decision 2), and the Excel template buttons
(Slice 1.26). The library shows the versions of a framework plainly, without crosswalk text.

## Consequences

- Imported frameworks are never templates (the importer refuses them), so the library has no
  "template" cards. Blank templates stay on the Import page; the library links to it for people
  who can import.
- Each tree open is one request plus one grouped child count and one mapping lookup for the rows
  returned, so cost follows what is on screen, not the size of the framework.
- Cross-references between items, the crosswalk view and the item's tags are not shown yet.
