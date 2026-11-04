# Coverage and gap reports

How well is a framework covered by the curriculum, where is it thin, and which objectives are not
mapped at all? Open **Reports** in the menu. The design is in
[ADR 050](../adr/050-coverage-engine.md). You need the `reports.view` permission for the programme
(or for a module, for a report on that module only).

**Every report says how its figures were made**: the method and its definition (with this
institution's numbers in it), the framework, the version and the time it was made.

## What counts

* **Only accepted links.** A suggestion, or a link waiting for a second review, is not coverage until a
  person has accepted it. These are counted apart, per item, as *waiting*, so a gap can say "two
  suggestions are waiting for review".
* A link with a coverage of 0 covers nothing and is not counted.
* **Links accepted in bulk** are counted, and marked: an item says when *all* its links were accepted
  in bulk (nobody read them), and the summary gives the total. So are **links that need a re-check**
  (the objective's wording changed since).
* Only objectives you may see. If that is not the whole version, the report says so.

## The four methods

Choose one at the top of the page. The definition under the choice is the exact rule.

| Method | An item with nothing below it is covered | A group (an item with items below it) |
|---|---|---|
| **Single match** | with one accepted link | by its own links only |
| **Multiple match** | with at least N accepted links (3 by default); fewer is *partial* | by its own links |
| **Subordinate match** | as single match | when at least 50% of the items below it are covered by a single match |
| **Weighted content coverage** | each link counts for its coverage score out of 5, and half of that when its depth is *below* the target; an item's links add up to at most 100%; covered from 40% | the better of its own links and the average of the items below it |

The numbers in bold (3, 50%, half, 40%) are settings of the institution: `multiple_match_n`,
`subordinate_min_percent`, `below_depth_percent` and `weighted_low_percent` in the `coverage` section of
the institution settings (there is no screen for them yet; the defaults are starting values that have
not been measured on a real programme).

## The coverage report

1. **Summary of the framework**: for each of the four methods, how many of the framework's items (those
   with nothing below them) are covered, partial or not covered. The method you chose is marked.
2. **Heatmap**: each row is a group of the framework (a top-level item), each column a phase, plus
   *All phases*, *Programme outcomes* and *Modules without a phase*. A cell is the average, over the
   items of the group, of how covered each is by the links of **that phase's** modules and sessions.
   Every cell prints its percentage, because the shade alone is not enough. Single and subordinate match
   give the same heatmap (the share of items with at least one link).
3. **Items**: the framework in tree order with each item's status, value, links, and flags (*all
   accepted in bulk*, *needs a re-check*, *suggestions waiting*). A group shows how many of its items
   are covered.

## The gap report

1. **Items with no or low coverage**: the items with nothing below them that the method does not call
   covered, those with no accepted link first, each with the groups above it, why it is a gap ("no
   accepted link", "1 of 3 accepted links") and how many suggestions are waiting.
2. **Objectives with no mapping**: objectives with no accepted link to this framework, and apart from
   them those that only have suggestions waiting (the quickest to close: review them). Each links to the
   objective in the curriculum builder.

## Reading the reports with care

* A framework **gap** is not necessarily a curriculum gap: the objectives may exist and not yet be
  mapped. Look at the number of objectives with no mapping first.
* Coverage reflects the accepted mapping, and an AI-assisted mapping with bulk acceptance can be
  generous or miss things; the flags are there to show that.
* The reports cover one version at a time; there is no comparison across years yet, and exports to Excel
  and PDF come in a later slice.
