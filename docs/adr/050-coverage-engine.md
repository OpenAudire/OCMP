# ADR 050: Coverage Engine, Coverage Report and Gap Report

## Status

Accepted (Slice 1.21). Builds on ADR 039 and 040 (what an accepted link is, bulk acceptance and its
marker), ADR 043 (links go with their objective: `live_link()`), ADR 027 (what a user may see) and
ADR 049 (the same visible-objectives scope as search). Brief, Phase 1 "Reports": "**Coverage
report**: per framework item and rolled up per group, using four labelled methods: single match
(≥1 accepted link), multiple match (≥N links, N configurable, default 3), subordinate match
(share of child items covered), and **weighted content coverage** (from coverage scores, reduced
when depth is below target). Heatmap of framework groups × phases. **Gap report**: framework
items with no or low coverage; objectives with no mapping." Every report states its method and date.

## Context

Mapping produces links; coverage is what committees ask about: "is the framework covered, where is
it thin, and what is not mapped at all?" The brief names four methods but not their exact
arithmetic. A number without its definition invites argument, and the data model carries two things
a naive count would hide: links accepted in bulk (nobody read them) and links whose objective
wording changed since (they need a re-check). This ADR fixes the arithmetic, the scope and the
labelling so the report can be audited.

## Decision

### 1. What counts

Only **accepted** links count. A link counts when it is live (`live_link()`), its objective is
live, not retired and shown to the user by their roles, and its **coverage is at least 1** (a
link that covers nothing covers nothing). Suggested links and links waiting for a second review
are **not** counted; they are counted separately per item as *waiting*, so a gap can say "two
suggestions are waiting for review". Rejected links are not counted anywhere.

Links accepted in bulk (`accept_method = bulk`) and links with `needs_recheck` are counted but
**flagged**: every item shows how many of its links are bulk-accepted or need a re-check, and says
so when *all* of its links were bulk-accepted. The summary shows the totals. (Brief section 8:
AI- or bulk-accepted links are marked in reports; CLAUDE.md since Slice 1.13.)

### 2. The four methods

Each is a labelled method, its definition is printed with the figures (with the institution's
numbers in it), and each gives an item a value from 0 to 1 and a status of covered, partial or none:

| Method | An item without items below it | A group (an item with items below it) |
|---|---|---|
| **Single match** | Covered with 1 or more accepted links | Its **own** links only; the items below are not looked at |
| **Multiple match** | Covered with N or more links (default 3); partial with fewer; value = links / N, at most 1 | The same, on its own links |
| **Subordinate match** | Same as single match | The share of the items below it **that have nothing below them** and are covered by a single match; covered from 50% (configurable), partial below, none at 0 |
| **Weighted content coverage** | Each link counts for its coverage score out of 5, and for 50% of that when its depth is *below* (configurable); an item's links **add up, at most 1**. Covered from 40% (configurable), partial below, none at 0 | The better of its own links and the average of the items below it |

The sums are deliberately simple and explainable: "five links of coverage 2 on one item are
covered, not five times covered". Alternatives (one minus the product of the gaps; a maximum) give
different numbers and were not chosen. A link without a stated depth is not reduced.

Settings, `settings["coverage"]` (typed, with defaults, in `policies.CoveragePolicy`):
`multiple_match_n` 3 (1 to 20), `subordinate_min_percent` 50, `below_depth_percent` 50,
`weighted_low_percent` 40. There is no screen for them yet (as for the mapping settings); they are
changed through the institution settings API.

### 3. The report

`GET /curriculum-versions/{id}/coverage?framework_id=…&method=…` returns:

* the method, its definition, the institution's numbers, the version, the framework, the time it
  was made, and whether the user sees only part of the version (`partial`);
* **a summary** of the whole framework for all four methods (items covered, partial, uncovered, out
  of the items that have nothing below them), and the link totals (accepted, bulk, to re-check,
  waiting);
* **one row per item** in tree order with its links, bulk and re-check links, waiting suggestions,
  distinct objectives, value and status, and for a group how many of its items are covered;
* **a heatmap of the framework's groups (top-level items) by phase**: each cell is the average, over
  the items of the group that have nothing below them, of the item's value *using only the links
  whose objectives belong to that phase*; plus a column for all phases together. Columns are the
  phases in order, "programme outcomes" and "modules without a phase". An objective belongs to the
  phase of its module (a session's objective to its module's phase). Single match and subordinate
  match give the same figure in the heatmap (the share of items with at least one link).

### 4. The gap report

`GET …/coverage/gaps` returns **the items that have nothing below them and are not covered** by the
chosen method, those with nothing first, each with the groups above it, the reason in words
("no accepted link", "1 of 3 accepted links") and its waiting suggestions; and **the objectives
with no accepted link to this framework**, in two lists: those with nothing, and those that only
have suggestions or reviews waiting (the quicker wins). The lists are capped at 200 objectives each
and the totals are returned.

### 5. Who sees what

Both need `reports.view` at the version's programme, **or** at a module of it for a narrower view;
anyone else who can see the version is refused (403) and a version they cannot see is a 404. The
figures cover only the objectives the user's roles show, and say `partial` when that is not the
whole version, so a module coordinator gets a report on their module and is told so.

## What this does not do

* Export to Excel or PDF (Slice 1.22; the same functions will feed it).
* Compare two versions or two frameworks, or show trends.
* Cover crosswalks (links to one framework do not count towards another).
* Change a number for you: the defaults are starting values, not measured on a real programme.
* A settings screen for the four numbers.

## Consequences

* The arithmetic is in one pure module (`coverage_engine.py`, tested without a database) and the
  report reads the database once for items, once for links.
* A different definition of any method later is a visible change in every report; the definition
  printed with the figures is the contract.
