# The mapping workspace

The **Mapping** page is where people link objectives to framework items by hand and say how well
each objective covers the item. The design is in [ADR 039](../adr/039-mapping-workspace.md). The
framework side is the same tree and search as the [framework library](frameworks.md).

## The three panes

1. **Objectives** (left): every objective of the chosen version that you may see. Filter by module,
   by phase, or to the objectives that have no links yet. Each shows how many links it has and
   whether any needs a look.
2. **Links of the selected objective** (middle): each link with its framework item, coverage in
   words, depth, status and reason. Edit, remove or (for reviewers) confirm a link here.
3. **Framework** (right): choose a framework, search or browse the tree and select an item. Under
   the item you see which other objectives are mapped to it.

Choose the version with the version button at the top. Only a **draft** version can be changed; a
published or archived version can be read but its links cannot be changed (copy it forward to make a
draft).

## Making a link

1. Select an objective on the left.
2. Select an item on the right and press **Link to the selected objective**. (There is no
   drag and drop: everything works with the keyboard or a single click.)
3. Choose a **coverage** from 0 to 5 and a **depth**, add a short reason if you like, and press
   **Add link**.

To change a link, press **Edit** on it (or **Edit this link** under the item). To take it away press
**Remove**; you are asked first. If the AI suggested the link, removing it rejects it instead, so it
stays as an example, and only a reviewer may do that.

### Coverage

Coverage says how much of the framework item the objective teaches. The scale is the product owner's
choice, based on the Charité scale (Theurich et al. 2025, GMS Journal for Medical Education 42(4):
Doc46; the citation has not been checked by the project):

| Level | Meaning |
|---|---|
| 0 | None (0%) |
| 1 | 1 to 20% |
| 2 | 21 to 40% |
| 3 | 41 to 60% |
| 4 | 61 to 80% |
| 5 | 81 to 100% |

### Depth

Depth compares the objective's Bloom or Miller level with the level the item expects.

- **Below**: the objective asks for less than the item expects. Example: the item says "manages",
  the objective says "describes".
- **Matches**: the same level.
- **Above**: the objective goes beyond what the item expects.
- **Not applicable**: the item states no depth and implies none, such as a keyword or a topic list.
  No penalty applies. If the item states no depth but has a verb, judge from that verb.

The weighted coverage report (a later slice) reduces a link's score by one point when its depth is
Below. The **?** on the page and in the dialog explains both words.

## What happens to a link you make

| You | Link becomes |
|---|---|
| May review mappings for this objective (`mapping.review`) | **Accepted** at once |
| The same, and the institution uses a second review (four-eyes mode) | **Waiting for a second review**; it counts only when a different reviewer accepts it |
| May map but not review (`mapping.edit` only) | **Suggested**; a reviewer decides on it in the review queue |

Changing coverage, depth or the reason makes the link a new claim, so it is decided again by the same
rules: a reviewer's edit of an accepted link in four-eyes mode goes to a second review, and an edit
by someone who may not review returns it to suggested. Saving without changing anything changes
nothing. Adding a link for an item whose earlier link was rejected reopens that link.

### Links flagged "Wording changed: check it still fits"

When an objective's wording is edited, its accepted links are flagged. Editing a link does **not**
clear the flag. A reviewer reads the new wording and presses **Still fits** to confirm; that is
recorded in the change history. Reports show the flag.

## Who may do what

- Reading needs access to the version (the same rules as the curriculum screens: you see what your
  roles show). What you cannot see does not exist as far as the page is concerned.
- Making, changing and removing links needs `mapping.edit` at the objective: its programme (for
  programme outcomes), module or session. A role held higher up also counts. The module coordinator,
  the programme director, the curriculum office and the mapper roles have it.
- Confirming a link and rejecting an AI suggestion need `mapping.review`.
- Every change is recorded in the change history (audit log) as `mapping.link_add`,
  `mapping.link_update`, `mapping.link_remove` or `mapping.recheck_confirm`.

The institution's second-review setting is `settings["mapping"]["four_eyes"]` (off by default); see
[ADR 016](../adr/016-mapping-data-model.md).
