# ADR 040: The Review Queue, Second Review and Bulk Accept

## Status

Accepted (Slice 1.13). Builds on ADR 012 (permissions), ADR 016 (mapping data model and review
workflow), ADR 017 (audit log), ADR 027 (curriculum read access), ADR 030 (versions), ADR 032
(re-check flag) and ADR 039 (mapping workspace).

## Context

Links have a review workflow in the service layer since Slice 0.12 (`app/services/mapping.py`), but
nobody could use it: there was no queue, no endpoint to decide, and the sidebar count was an empty
slot. Slice 1.12 made suggestions by people who may map but not review, and recorded that such a
suggestion has no named reviewer until a queue exists. The brief (section 6) asks for a review queue
"sorted by confidence" showing the objective, framework item, rationale and evidence quote, with
keyboard shortcuts (A accept, R reject, E edit, S skip, 2 send to second review), bulk accept above a
chosen confidence and a progress counter, and an optional four-eyes mode where a second reviewer must
agree and disagreements are flagged.

## Decision

### What waits for a person (three piles)

| Pile (`stage`) | Links | Needs |
|---|---|---|
| `first` | status `suggested`: made by the AI or a migration, or by someone who may map but not review | `mapping.review` at the objective's scope |
| `second` | status `needs_second_review` | `mapping.second_review` at the objective's scope |
| `recheck` | `accepted` with `needs_recheck` (the objective's wording changed, ADR 032) | `mapping.review` |

Only objectives of **draft** versions that the user may see are listed (ADR 027, ADR 030). A link in
a published or archived version cannot be decided (409). Deleted objectives, sessions, modules and
frameworks drop out. The queue reveals nothing the curriculum screens do not: what the user cannot
see is not listed, and an action on it answers 404.

`mapping.second_review` is the permission the catalogue already had for this: the mapper, programme
director, curriculum office and platform admin roles hold it; the module coordinator does not (the
brief gives coordinators "review AI suggestions", and the mapper "first and second review").

### Endpoints (`app/api/v1/mapping_review.py`, `app/services/mapping_review.py`)

- `GET /mapping/review-queue?stage=&version_id=&framework_id=&module_id=&min_confidence=&max_confidence=&sort=&offset=&limit=`:
  a page of one pile (50 by default, 100 at most), sorted by confidence (highest first by default,
  lowest first, or by module; links without a confidence come last), with `progress` (accepted,
  rejected, second review and waiting suggestions of the chosen version, framework and module),
  `counts` per pile, the filter choices that exist (`facets`) and the institution's `four_eyes`.
- `GET /mapping/review-queue/count`: the same counts for the sidebar. The sidebar shows the **total of
  the three piles**: everything waiting for this person.
- `POST /mapping-links/{id}/review` with `decision` (`accept`, `reject`, `second_review`), the
  `expected_status` the person saw and, when accepting, an optional corrected `coverage` and
  `depth_match` ("edit and accept"). A link that is no longer in the status the person saw is a
  **409**, so a first review can never turn into a second review by accident when two people work at
  once. Accepting needs a coverage and a depth (422 otherwise); corrections with anything but an
  accept are refused (422). Audit labels: `mapping.review_first_accept`,
  `mapping.review_first_accept_edited`, `mapping.review_second_accept`,
  `mapping.review_second_accept_edited`, `mapping.review_reject`, `mapping.review_send_second`.
- `POST /mapping/review-queue/bulk-accept` (below).
- Confirming that a link in the re-check pile still fits uses the existing
  `POST /mapping-links/{id}/recheck` (`mapping.review`, `mapping.recheck_confirm`).

No reviewer or author names are returned. A second reviewer sees only *what* the first reviewer
decided (accepted, rejected, unsure), not who.

### Four-eyes in the service, not the screen

The rules are in `mapping.review_link`, called by the endpoint:

- In four-eyes mode a first accept does not accept: the link goes to `needs_second_review` with the
  reviewer as first reviewer. With `second_review_for_rejects` a first reject does too; "unsure"
  (`second_review`) always does.
- The second reviewer must be someone other than the first reviewer (**409**). Following ADR 016
  ("hand-made links count as reviewed by their author"), the **author of a hand-made link also cannot
  give its second review**, even when someone else gave the first (this is new in this slice: before,
  only the first reviewer was excluded). The database already refuses equal first and second
  reviewers.
- A second decision that overturns the first accept or reject sets `needs_discussion` (the flag shown
  in the workspace and the framework browser). "Unsure" is not a decision to overturn.
- The queue does not list a link the user may not second (their own first review or their own
  hand-made link), and the count leaves it out; the progress card still counts it as "second review".

### Bulk accept: the safety rules

"Accept all N and above" (`dry_run` counts first; the screen always shows the count and the rules
before the person confirms):

1. The threshold may not be below **80%** (`BULK_MIN_CONFIDENCE`; the mockup calls under 65% "check
   carefully"). The screen offers 80, 85, 90 and 95%, default 90%.
2. Only **first-stage** suggestions with a confidence, a coverage and a depth are touched. Second
   reviews and re-checks are never accepted in bulk, so bulk accept cannot be a second pair of eyes.
   Links made by a person have no confidence, so they are always decided one by one.
3. Only links the user may review (permission, visibility and draft version) and did not author.
4. Within the filters on the screen (version, framework, module) and at most **200** links
   (`BULK_MAX_LINKS`) at a time, the most confident first; the rest wait for the next batch.
5. In four-eyes mode it is a **first review**: each link goes to `needs_second_review` with the person
   as first reviewer and still needs a different second reviewer. Without four-eyes the links are
   accepted with accept method `bulk`, so reports can tell them from individual decisions.
6. One audit operation, `mapping.review_bulk_accept`, with the number and the threshold as its
   reason, around the per-link audit entries.

### The screen (`frontend/src/review/`, `/mapping/review`)

As in the mockup: a progress card (reviewed of total, accepted, rejected, second review, waiting; a bar
that is also given in words), filters (pile, confidence, module, version and framework when there is a
choice, order), the list of suggestions as cards and the selected suggestion beside it: the objective
with the evidence quote marked, the suggested item with its group, the reasoning, the coverage 0 to 5
and the depth to correct, and **Accept**, **Second review**, **Reject** and **Skip** buttons. For
suggestions made by a person the AI-only parts render sensibly: the heading is "Why this link was
suggested", there is no confidence bar (a line says it was suggested by a person) and no highlighted
evidence unless a quote exists. The pile "wording changed" shows the objective and the item, the
**Still fits** button and a link to the mapping workspace. The Phase 2 items of the mockup are not
shown ("also mapped from N other objectives" would count objectives the user may not see).

**Keyboard shortcuts** (A accept, R reject, E edit, S skip, 2 second review): to meet the WCAG 2.1.4
rule on single-character shortcuts they work only while focus is inside the list or the details
(never on the page as a whole, never in a text field, and not with Ctrl, Alt or Meta held), they are
listed on the page beside a **switch that turns them off** (kept in this browser), and every action is
also a button (`aria-keyshortcuts` is set). **E** moves focus to the coverage choice so it can be
changed with the arrow keys; **A** then accepts with the chosen values. After a decision the next
suggestion is selected and focused so the keys keep working; the result is announced in a status
region. Screen readers that capture letter keys in browse mode do not pass them to the page, which is
why the buttons and the switch matter.

## Consequences

- The AI pipeline (Slice 1.16) only has to create `suggested` links with a run, a confidence, a
  rationale and an evidence quote; they appear here without further work.
- Reopening a rejected link (`mapping.reopen`, exists in the service) has no screen yet.
- Progress is computed over the links of the user's scope that the AI or a migration made, plus any
  link waiting for a person; hand-made links accepted at once are not "suggestions".
- The queue loads the small candidate rows of a user's drafts and filters them in memory by scope
  permissions, like the mapping workspace; with tens of thousands of waiting suggestions this should
  move into SQL.
