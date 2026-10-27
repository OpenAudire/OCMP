# ADR 039: The Mapping Workspace, the Coverage Scale and Depth

## Status

Accepted (Slice 1.12). Builds on ADR 012 (permissions), ADR 016 (mapping data model and review
workflow), ADR 017 (audit log), ADR 027 (curriculum read access), ADR 030 (versions), ADR 031
(objective scope), ADR 032 (re-check flag) and ADR 038 (framework browser).

## Context

Mapping links existed as a table and a review service (Slice 0.12) but nobody could make one. The
brief asks for a workspace with objectives on the left, the framework tree on the right and the
links between them; "manual linking by drag or search"; coverage 0 to 5 and a depth match on every
link "with short help text explaining the scale" (sections 6 and 11).

The brief names the coverage range and the depth values (below, matches, above) but gives no wording
for the scale or the depth. The product owner supplied it on 2026-10-27 (below).

## Decision

### The coverage scale (the product owner's choice)

The scale is the Charité scale, as given by the product owner, who cited Theurich T, Holzhausen Y, Ahlers O, Peters H. GMS J Med Educ. 2025;42(4):Doc46. DOI 10.3205/zma001770:

| Level | Meaning |
|---|---|
| 0 | none (0%) |
| 1 | 1 to 20% |
| 2 | 21 to 40% |
| 3 | 41 to 60% |
| 4 | 61 to 80% |
| 5 | 81 to 100% |

The citation was **verified by the product owner on 2026-10-27**; the project itself has not
fetched it. The scale replaces the looser anchors in the review-queue mockup ("0 none, 1 up to 20%, 3 about
half, 5 more than 80%"). The words are in `frontend/src/i18n/locales/en.json` under
`mapping.coverage.levels`.

### Depth

Depth compares the objective's Bloom or Miller level with the level the framework item expects.

- **Below**: the objective asks for less than the item expects (the item says "manages", the
  objective says "describes").
- **Matches**: the same level.
- **Above**: the objective goes beyond what the item expects.
- **Not applicable** (new): the item states no depth and implies none, such as a keyword or a topic
  list. It carries no penalty. If the item states no depth but has a verb, the mapper judges from
  that verb.

The brief listed three values. The fourth is stored as `not_applicable`: migration `0018` replaces
the CHECK constraint on `mapping_links.depth_match` (the downgrade sets such rows to null, "not
judged"). The enumeration lives in one place (`DepthMatch` in `app/models/mapping.py`) and the API
schemas and the demo loader use it. The pack schema holds no mapping links, so it needed no change;
the AI mapping pipeline (Slice 1.16) must offer all four values when it is built.

**Weighted coverage (a later report, not built here):** the weighted content coverage reduces a
link's score by one point when its depth is Below (the Charité method). Not applicable and Above
reduce nothing. This is recorded here so the report in Slice 1.24 uses it; nothing computes it yet.

### Help text

The text of the "?" is the product owner's, word for word (`mapping.help.text`):

> Coverage: how much of this framework item the objective teaches, from 0 (none) to 5 (more than
> 80%). Depth: whether the objective asks students to work at the level the item expects (for
> example, knowing versus doing). Both affect the weighted coverage report.

Beside it the screen lists every level and the four depth definitions. The dialog also shows the
wording of the selected level and depth, so the help is not hidden behind the "?" alone.

### Who may do what

All checks are in the API; the screen only shapes the buttons.

- **Reading** the workspace (`GET /curriculum-versions/{id}/mapping`) shows the objectives of the
  version that the user may see (ADR 027; not visible is 404) with their links, and per objective
  whether the user holds `mapping.edit` and `mapping.review` at that objective's scope. Rejected
  links are left out (they are not mappings, ADR 038).
- **Making, changing and removing a link** needs `mapping.edit` at the objective's scope
  (`objective_scope`, ADR 016: the programme for programme outcomes, the module, or the session;
  roles held higher up count). An objective the user cannot see is 404, not 403. Only objectives of
  **draft** versions can be changed (409 otherwise, ADR 030).
- **Confirming that a link still fits** (the re-check flag, ADR 032) needs `mapping.review` and is a
  separate action. Editing a link never clears the flag; only confirming does.
- Services are in `app/services/mapping_links.py`; the router is `app/api/v1/mapping.py`. Each
  change is labelled in the audit log: `mapping.link_add`, `mapping.link_update`,
  `mapping.link_remove` (and the existing `mapping.recheck_confirm`).

### Status of a hand-made link

This follows the review workflow of ADR 016 and the institution's four-eyes setting.

- A person holding `mapping.review` at the objective's scope has their link **accepted** at once
  (accept method "individual", they are the first reviewer). With **four-eyes mode** it goes to
  **needs second review** instead, with them as the first reviewer.
- Anyone else who holds `mapping.edit` makes a **suggestion** (status suggested, nobody has decided
  on it). A reviewer decides on it in the review queue (Slice 1.13). The author is recorded as the
  creator (`created_by_id`); they are not set as a reviewer, because a first reviewer on an
  undecided suggestion would be overwritten at the first review anyway.
- **Changing** coverage, depth or the reason is a new claim. By a reviewer the link is accepted again
  (or, in four-eyes mode, goes to a second review, also when it was accepted). By anyone else it
  returns to suggested. An edit that changes nothing does not change the status.
- **Adding** a link for a pair whose earlier link was **rejected** reopens that row (one row per
  objective and item): its source becomes human, the AI's confidence and quote are cleared, and its
  status follows the rules above.
- **Removing** a link made by a person or imported deletes it. A link the AI suggested or a
  migration made is **rejected** instead (it stays as an example for later AI runs, ADR 016), and
  that needs `mapping.review`.

### The screen

`/mapping/:versionId` has three panes, as in the mockup: objectives with filters (module, phase and
"only those without links") on the left, the selected objective's links in the middle, the
framework (the same tree and search as the Frameworks page, with a framework chooser) on the right.
Phase 2 items of the mockup are not shown. Linking is by button: select an objective, select an
item, press **Link to the selected objective**, and choose coverage and depth in a dialog. There is
no drag and drop, so every action works by keyboard and single pointer. Existing links are shown per
objective (middle pane) and per framework item (the "where mapped" list under the item).

## Consequences

- The review queue (1.13) works on links in the states described here; the AI pipeline (1.16) creates
  suggestions with all four depth values.
- A suggestion by someone who may not review has no named reviewer until a reviewer decides on it in
  the review queue (Slice 1.13, [ADR 040](040-review-queue.md)); it is visible in the workspace as
  "Suggested, not reviewed".
- The coverage wording and depth definitions are one translation block each, so a different
  institution scale would be a translation and report change, not a schema change; the stored value
  stays an integer 0 to 5.
