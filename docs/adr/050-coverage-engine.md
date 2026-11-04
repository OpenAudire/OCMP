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

### 2. The four methods (amended by Slice 1.21a)

Slice 1.21 chose the sums itself. The owner then required them to **match Theurich et al. 2025 so
that our figures are comparable with theirs**, and Slice 1.21a replaced them with the definitions
below. They were taken from the owner's specification; **the paper itself was not read by us**, so
a difference between this text and the paper is possible and should be reported.

Throughout, an **item** is a framework item with nothing below it and a **group** is an item with
items below it. Every method has a **headline** for the whole framework and a figure for each item
and group; the definition is printed with the figures (with the institution's numbers in it).

| Method | Item | Group | Headline |
|---|---|---|---|
| **Single match** | Covered (yes or no) with 1 or more accepted links | The share of the items below it that are covered | The share of items covered |
| **Multiple match** | Covered (yes or no) with N or more accepted links (N = 3); **no partial credit** | The share of the items below it that are covered | The share of items covered |
| **Subordinate match** | Same as single match | The percentage of the items below it covered by a **single match** | The **average of those percentages over the groups** (not defined when there is no group) |
| **Weighted content coverage** | Each link scores its coverage out of 5; a depth of *below* takes **one point** off (of the five, as approved in Slice 1.12); an item's links **add up to at most 1** | The average of the items below it | The **average over the items**: the "degree of coverage" |

**Group figures are built up from their items for every method.** Links made directly to a group
are counted, shown on the group's row and in the summary ("made to the group itself, not
counted"), and **do not count towards any figure**, so nothing is counted twice. (Slice 1.21 judged
a group by its own links under single and multiple match and gave weighted coverage the better of
the two; both are gone.)

Two settings no longer change a figure and only decide what the **gap report lists**:
`subordinate_min_percent` (50: the groups under it are listed, for subordinate match only) and
`weighted_low_percent` (40: the items under it are listed, for weighted coverage). The setting
for half credit below the target depth (`below_depth_percent`) is removed: the rule is one point.
`multiple_match_n` (3, 1 to 20) stays. Settings are `settings["coverage"]`
(`policies.CoveragePolicy`), changed through the institution settings API; there is no screen.

The statuses still exist for the gap report (covered, partial, none), but the figures the reports
lead with are the percentages.

### 3. The report

`GET /curriculum-versions/{id}/coverage?framework_id=…&method=…` returns:

* the method, its definition, the institution's numbers, the version, the framework, the time it
  was made, and whether the user sees only part of the version (`partial`);
* **a summary** of the whole framework for all four methods: each method's **headline** and the
  counts behind it (of items, or of groups for subordinate match), and the link totals (accepted,
  made to groups, bulk, to re-check, waiting);
* **one row per item** in tree order with its links, bulk and re-check links, waiting suggestions,
  distinct objectives, value and status, and for a group how many of its items are covered and the
  links made to the group itself (apart, not counted);
* **a heatmap of the framework's groups (top-level items) by phase**: each cell is the average, over
  the items of the group that have nothing below them, of the item's value *using only the links
  whose objectives belong to that phase*; plus a column for all phases together. Columns are the
  phases in order, "programme outcomes" and "modules without a phase". An objective belongs to the
  phase of its module (a session's objective to its module's phase). Single match and subordinate
  match give the same figure in the heatmap (the share of items with at least one link).

### 4. The gap report

`GET …/coverage/gaps` returns **the items that are not covered** by the chosen method (for weighted
coverage: under the low line), those with nothing first, each with the groups above it, the reason in
words ("no accepted link", "1 of 3 accepted links") and its waiting suggestions; for subordinate match
also **the groups under the share set** (`group_gaps`); and **the objectives
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
* Claim equality with the study it follows: the definitions come from the owner's specification of it.
* A settings screen for the four numbers.

## Consequences

* The arithmetic is in one pure module (`coverage_engine.py`, tested without a database) and the
  report reads the database once for items, once for links.
* A different definition of any method later is a visible change in every report; the definition
  printed with the figures is the contract.
