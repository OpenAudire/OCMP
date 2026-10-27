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
director, curriculum office and platform admin roles hold it. **The module coordinator holds it too,
at module scope** (product owner decision, Slice 1.14a; see the amendment at the end).

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

## Amendment: product owner review (Slice 1.14a, 2026-10-27)

The product owner approved the Slice 1.13 decisions with these changes.

1. **Module coordinators give second reviews in their own module.** `module_coordinator` gains
   `mapping.second_review` (system role in `app/core/permissions.py`, which `sync_system_roles` applies
   on a new install, plus the data migration `0020`, which adds it to the stored system role on an
   existing install and leaves custom roles alone). The four-eyes rules are unchanged and still
   enforced in the service: nobody gives the second review of a link they reviewed first, or of a
   hand-made link they wrote. A coordinator who gave the first review therefore does not see that link
   in the second pile and gets 409 if they try; a different coordinator or mapper must.
2. **The floor and the cap of "Accept all" are institution settings.** `settings["mapping"]` gains
   `bulk_accept_min_percent` (50 to 100, default 80) and `bulk_accept_max_links` (1 to 1000, default
   200), validated by `MappingPolicy` and read through `institution_settings`. The API reports them in
   `bulk_min_confidence` and `bulk_max_links`; the dialog offers the floor first, then 85, 90 and 95
   above it, and the button starts at 90% or the floor if that is higher. There is no settings screen
   for the mapping section yet (it is changed through the settings API, as for the review policy and the
   credits section), so there is none for these two either.
3. **Bulk-accepted links carry a durable marker.** `MappingLink.accept_method` (it already held
   `individual`, `bulk`, `automatic` and `imported`) is `bulk` for a link accepted by "Accept all". It is
   audited (the update entry carries the operation `mapping.review_bulk_accept`) and returned as
   `accept_method` by the queue and the mapping workspace. Screens show it as the text "Accepted in
   bulk" (with an icon, never colour alone). **Reports (Slice 1.21) must show it**; none exists yet.
   A person supersedes it: reviewing or editing the link individually (a second reviewer's accept, a
   hand edit in the workspace, "Still fits") sets `individual`. In four-eyes mode a bulk accept is only
   a first review, so the link ends as `individual` once a second person accepts it; the bulk step
   stays in the audit log. This is the least risky reading: the marker means "no person has looked at
   this link on its own", so it goes away only when a person did.
4. **The sidebar count is what the user can act on now.** `counts.waiting` is the first-review pile
   plus the second-review pile, with the same rules as the piles: first review needs `mapping.review`,
   second review needs `mapping.second_review` and excludes links the user reviewed first or wrote.
   **Re-checks are not counted**: they are accepted links, not suggestions waiting for review (`total`
   still includes them for the page). The badge is hidden at 0 and reads "99+" above 99; its accessible
   name is "N suggestions waiting" (plural-aware) or "more than 99 suggestions waiting".
