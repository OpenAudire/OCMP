# ADR 052: Redundancy and Traceability Reports

## Status

Accepted (Slice 1.23). Builds on ADR 051 (report documents and exports), ADR 044 (stored
near-duplicate pairs), ADR 033 (the near-duplicate threshold) and ADR 027 (what a user may see).
Brief, Phase 1 "Reports": "**Redundancy report**: items covered by unusually many events;
near-duplicate objectives across modules. **Traceability report**: programme outcome → module
outcomes → session objectives → mapped framework items."

## Context

Two questions a curriculum committee asks that neither the coverage report nor the gap report
answers: *where are we teaching the same thing again and again?* and *can every session be traced up
to a programme outcome and across to the framework?* The brief names the reports but not what
"unusually many" means, so that has to be stated.

## Decision

Both reports are builders of `ReportDoc` (ADR 051): they have a screen, an Excel export and a PDF
export, state their method and date, and show only what the reader's roles show (ADR 027).

### Taught in many sessions (the redundancy report; needs a framework)

**Amended in Slice 1.24a (ADR 053).** The report is labelled **"Taught in many sessions"** (it does not say
that repeating is wrong). The two numbers below are now institution settings (`settings["coverage"]`:
`repeat_min_sessions`, default 4, and `repeat_spread`, default 1.5) and are printed on the report. A
programme coordinator (`curriculum.edit` at the programme) can mark an item as an **intentional repeat
(spiral curriculum)** with a reason: audited (`intended_repeats`, operations `reports.intended_repeat_mark`
and `_unmark`), per programme (all versions), removed from the list and shown in its own table with the
reason. Removing the mark lists the item again.

1. **Framework items taught in unusually many sessions.** For each item of the chosen framework: the
   number of distinct **sessions** (learning events) that have an objective with an *accepted* link
   to it (coverage 1 or more), and the number of distinct modules (module outcomes count towards
   the module). An item is listed when its session count is **at least the larger of 4 and, when
   five or more items are taught at all, the average plus 1.5 standard deviations** of the
   session counts of the items taught. The report prints the threshold it used and how many items
   are taught. Both numbers (4 and 1.5) are constants chosen to be easy to explain, **not measured on
   a real programme**; many sessions is a thing to look at (it can be a thread, a spiral, or overlap),
   not a finding. Each listed item names up to eight of its sessions.
2. **Near-duplicate objectives in different modules.** From the stored similarities (the same pairs
   and the institution's threshold as the objective checker, ADR 033 and 044), the pairs of
   objectives whose modules differ, most similar first, each side with its module and session. They
   exist only where the embeddings service is on and `embed-all` has been run; the report says so.

### Traceability report (a framework is optional)

Follows the **upward links** between objectives, from each programme outcome down: programme
outcome → the module outcomes linked up to it → the session objectives linked up to those, and the
session objectives linked directly to the programme outcome. One row for each path, ending in the
framework items the last objective of the row is **accepted** for (all frameworks, each item
prefixed by its framework's name, or only the chosen one). A programme outcome with nothing below it
has a row that says so. A second table lists the **module outcomes and session objectives no
programme outcome reaches** (or whose programme outcome the reader cannot see): the traceability
gaps. Cut at 5 000 rows.

A person who does not see the whole version cannot see the programme outcomes, so for them the first
table is empty and the second lists what they can see; the report says it covers only part of the
curriculum.

## What this does not do

* Say whether repetition is *wrong*, rank sessions, or compare with other programmes.
* Use the meaning of the sessions' titles or descriptions: sessions are compared through their
  objectives only.
* Show links that are only suggested or waiting for review.
* Translate the tables (ADR 051).

## Consequences

* Two builders and two registry entries; screens, exports and access come from ADR 051.
* The traceability report shows an honest picture of unfinished work: objectives extracted from
  a study guide appear as "not linked upward" until a person links them.
