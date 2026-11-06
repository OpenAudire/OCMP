# ADR 061: Showing Students Where a Year Builds Each Competency

## Status

Accepted (Slice 1.31, the product owner's review of 1.29). Builds on ADR 059 (the explorer), ADR 027 (what a
person may see) and ADR 050 (group arithmetic).

## Context

ADR 059 kept framework mappings out of the explorer: a student could read an unreviewed or bulk-accepted link
as a promise. The product owner decided that an institution may choose to show students "where this year builds
each competency", as long as it is off until chosen and stays thin.

## Decision

**An institution switch, off by default.** `settings["explorer"].show_competency_view`
(`policies.ExplorerPolicy`, edited under Admin > Institution settings > Student explorer). While it is off the
endpoint answers 404 and the explorer has no such view.

**What it shows.** `GET /curriculum-versions/{id}/explorer/competencies` (`services/explorer_competencies.py`):
for each framework in use, each **competency group**, and under it the modules and sessions of the published
version that carry it.

* **Published versions only**, and only what the person's roles show (`visible_version`,
  `search.visible_objective_ids`, so retired objectives are left out). A draft is a 404.
* **Accepted links only**, with a coverage of at least 1, through `live_link()`. Suggested, second-review and
  rejected links are not used. A link flagged **needs re-check** is also left out (its objective's wording has
  changed since it was accepted). Links accepted in bulk or by an import **are** accepted links and count;
  students are not told how a link was accepted.
* **Competency-group level only.** A group is a top-level framework item with items below it. A link to any item
  below counts for its group; a link made to the group itself places nothing (as in the coverage reports,
  ADR 050). The answer holds group codes and titles and nothing below them: no item codes, titles or counts.
* **No scores.** No coverage, depth, confidence, number of links, percentage, status or reviewer.
* A module outcome places its module (with no sessions listed); a session objective places its session and
  module. Programme outcomes belong to no module and place nothing.
* A group with nothing linked is listed with a neutral sentence ("Nothing in this year is linked to this group
  yet"). A framework with no group placed at all is left out.

**Screen.** A third view in the explorer, *Competencies*, shown only while the switch is on. Each group is a
heading; its modules link to the module page and its sessions to the module page with the session marked.

## Consequences

* The explorer still needs only `curriculum.view_published`.
* Turning the switch on is the institution's decision that its accepted mapping is fit to be read by students;
  the admin help says so. A year whose mapping is not reviewed will show little, or an incomplete picture.
* Nothing is stored; the read is a handful of queries per framework.
