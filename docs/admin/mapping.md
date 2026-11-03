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
choice, based on the Charité scale (Theurich T, Holzhausen Y, Ahlers O, Peters H. GMS J Med Educ. 2025;42(4):Doc46. DOI 10.3205/zma001770; citation verified by the product
owner, 2026-10-27):

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

## Suggesting links with AI

People who hold **AI run** and **mapping edit** (programme directors and module coordinators) see a
**Suggest links with AI** panel on a draft version. It is not there when AI is off for the
installation, you cannot change the version, or you lack the rights. The design is in
[ADR 045](../adr/045-ai-mapping-pipeline.md).

1. Press **Suggest links with AI**, choose the **framework** and which **objectives** to map (every
   objective of the version, or one module). Start with one module to see what you get.
2. The run is queued and a background job asks the AI service about each objective. The panel
   shows the state in words (waiting, running, finished, stopped), a progress bar, how many objectives
   are done, how many suggestions were made and how many objectives could not be mapped. You can
   leave the page; the run goes on.
3. **Cancel run** stops it before the next objective. Suggestions already made stay.
4. When it ends, **Open the review queue**. Every suggestion is a link with the status
   *suggested*, marked as made by the AI, with coverage, depth, a confidence, a one-sentence reason and
   the words of the objective it is based on. **Nothing is accepted automatically.** People review
   them like any other link ([Review queue](review-queue.md)).

What the AI is asked: for each objective, about the ten framework items that fit it best (chosen by
meaning where the [embeddings service](../operations/embeddings.md) is on, and by words otherwise;
items the objective is already linked to, **including rejected ones**, are not asked again). When
people have already accepted or rejected links for similar objectives, a few of those decisions go
into the question as examples, so the AI learns what your institution counts. Only curriculum text is
sent and the [privacy guard](ai.md) applies as always: an objective whose wording looks like it holds
personal information is **not sent** and is counted as failed.

A run ends in one of these ways:

| It says | Meaning |
|---|---|
| Finished | Every objective was looked at. Some may have failed; the count is shown |
| Stopped with a problem | AI was switched off or restricted meanwhile, the provider failed several times in a row, or no objective could be mapped. The reason is shown |
| Stopped: monthly limit reached | The monthly or per-run limit in [AI settings](ai.md#budget) was reached. What was done stays; an administrator can raise the limit |
| Cancelled | A person stopped it |

The AI is asked to list **only the items that fit** and to keep each reason short. Four rules shape
what you see (the last two are settings, see [Basics](basics.md)):

- **The most specific item.** When the AI suggests an item and one of its children for the same objective,
  only the child is kept (`ai_prefer_specific_item`, on by default). You can still link a parent by hand.
- **Minimum coverage.** Suggestions that cover less than `ai_min_coverage` (default 1, meaning any) are
  dropped. A higher value gives fewer, stronger suggestions.
- **A depth comparison.** "Not applicable" depth is only allowed for items that state no verb or level (a
  keyword, a topic). For any other item the AI must say whether the objective is below, matches or is above.
- **Rejections stand, until the wording changes.** A link you rejected is not suggested again. If the
  objective's wording is edited after the rejection, the AI looks at that item again and may suggest it
  anew; you then decide again.

A call that fails because the provider is busy (rate limit, overload, timeout) is tried again up to twice.
If a run's background job is lost (for example the server restarted), the run shows *Stopped with a
problem* after about 20 minutes and you can start it again; suggestions already made stay.

Only one run for a version and framework can go at a time. A run costs one AI call for each objective
that has candidates, and one more when an answer has to be asked for again; it counts against the
budget. The quality of the suggestions is not yet measured (the evaluation tool comes in a later
slice): treat them as a first draft for reviewers, not as findings.

## What happens to a link you make

| You | Link becomes |
|---|---|
| May review mappings for this objective (`mapping.review`) | **Accepted** at once |
| The same, and the institution uses a second review (four-eyes mode) | **Waiting for a second review**; it counts only when a different reviewer accepts it |
| May map but not review (`mapping.edit` only) | **Suggested**; a reviewer decides on it in the [review queue](review-queue.md) |

Changing coverage, depth or the reason makes the link a new claim, so it is decided again by the same
rules: a reviewer's edit of an accepted link in four-eyes mode goes to a second review, and an edit
by someone who may not review returns it to suggested. Saving without changing anything changes
nothing. Adding a link for an item whose earlier link was rejected reopens that link.

### Links flagged "Wording changed: check it still fits"

When an objective's wording is edited, its accepted links are flagged. Editing a link does **not**
clear the flag. A reviewer reads the new wording and presses **Still fits** to confirm; that is
recorded in the change history. Reports show the flag.

## Deleting objectives and their links

When an objective is deleted, its mapping links are deleted with it, in the same step and under the
same label in the change history. This holds for every way an objective can go: deleting it
directly, deleting a session, a module or a draft version that holds it. Deleted links are not
counted anywhere: not in "where mapped" on the framework browser, not in the workspace, the review
queue or its sidebar number, not when copying a version forward, and they no longer stop you from
deleting a framework. A link you remove yourself is removed for good (as before); only links that
went with an objective can come back with it.

If an objective is ever restored, the links that were deleted with it are restored too (links
removed at another time stay removed). If a newer link for the same objective and item already
exists, it wins and the older one stays deleted.

### Tidying an install from before this rule

Installs that deleted objectives before this rule hold links of deleted objectives that still
count in places. Clean them up with the command below, run on the server. It only lists them unless
you add `--apply`; each link is soft-deleted through the application and recorded in the change
history as `mapping.orphan_cleanup`. It is safe to run again.

```
docker compose exec api python -m app.cli clean-orphan-links
docker compose exec api python -m app.cli clean-orphan-links --apply
```

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
