# The review queue

The **Review queue** (Mapping, then Review queue in the menu) is where people decide on mapping links
that nobody has accepted yet. The number beside it in the menu is how many links wait for you. The
design is in [ADR 040](../adr/040-review-queue.md); the links themselves are made in the
[mapping workspace](mapping.md).

## What waits for you

Choose the pile with **Show**:

| Pile | What it holds | You need |
|---|---|---|
| **Waiting for a first review** | Suggestions nobody has decided on: made by a colleague who may map but not review, or (once the AI is switched on) by the AI | `mapping.review` |
| **Waiting for a second review** | Links a first reviewer accepted (when the institution uses a second review), rejected (where rejects need a second look) or was unsure about | `mapping.second_review` |
| **Wording changed, to re-check** | Accepted links whose objective's wording was edited afterwards | `mapping.review` |

You see only links in **draft** versions, for objectives you may see and may review. A link in a
published version cannot be decided.

## Deciding

Select a suggestion in the list. The details show the objective (the words that are the evidence are
highlighted), the suggested framework item, why it was suggested and how sure the source was, and the
**coverage** (0 to 5) and **depth** as suggested. To correct them, choose other values; then:

- **Accept** accepts the link with the values chosen (edit and accept).
- **Second review** says you are unsure and asks another reviewer to decide (first pile only).
- **Reject** rejects it; a rejected link is kept as an example and is not a mapping.
- **Skip** moves on without deciding.

In the second pile you see what the first reviewer decided (never who), and you may agree or disagree.
If you disagree, the link is **flagged for discussion** (shown in the workspace and the framework
browser) so people talk it over before relying on it. In the re-check pile, **Still fits** confirms the
link against the new wording, or **Open in the mapping workspace** lets you change it.

Two people deciding at once is safe: if a link changed while you were looking at it, nothing is
saved, you are told, and the list refreshes.

## Keyboard shortcuts

| Key | Action |
|---|---|
| **A** | Accept (in the re-check pile: Still fits) |
| **R** | Reject |
| **E** | Edit: move to the coverage choice (arrow keys change it, then press A) |
| **S** | Skip to the next suggestion |
| **2** | Send to a second review |

The keys work only while focus is in the list of suggestions or the details (after you select a
suggestion, or after a decision, focus is there), not in the filters, not while you type, and not
with Ctrl, Alt or Meta held. Single-key shortcuts can get in the way of some assistive technology, so
the **Use keyboard shortcuts** switch above the list turns them off (the choice is kept in your
browser). Every action is also a button, and the buttons are always available.

## Accept all confident suggestions

**Accept all 90% and above** counts first, then accepts the waiting suggestions of the filters now set
(module, version, framework) in one go. The safety rules:

- not below 80% confidence (choose 80, 85, 90 or 95%);
- only first-pile suggestions that have a confidence score and that you may review and did not author;
  links a person suggested have no score and are always decided one by one;
- never second reviews or re-checks, so a bulk accept cannot stand in for a second pair of eyes;
- at most 200 at a time, the most confident first; run it again for the next batch;
- when the institution uses a second review, a bulk accept is only a **first review**: each link then
  waits for a different reviewer.

Bulk-accepted links are recorded as accepted by you in a bulk action, so reports can tell them from
individual decisions.

## The second review (four-eyes mode)

The institution setting `settings["mapping"]["four_eyes"]` (off by default, see
[ADR 016](../adr/016-mapping-data-model.md)) makes every accept a first review. A link counts as
accepted only when a **different** person with `mapping.second_review` agrees. Specifically:

- the person who gave the first review cannot give the second (the API refuses it, and the link is
  not in their queue);
- the person who wrote a hand-made link counts as its first reviewer and cannot give its second
  review either;
- a second decision that differs from the first (accept versus reject) flags the link for discussion.

`settings["mapping"]["second_review_for_rejects"]` also sends first-stage rejects to a second review.

## Who may do what

Every check is in the API; the screen only hides what would be refused. Deciding on a link you cannot
see answers "not found"; on one you can see but not decide on, "forbidden". Each decision is recorded
in the change history as `mapping.review_first_accept` (or `..._edited` when you corrected the
values), `mapping.review_second_accept`, `mapping.review_reject`, `mapping.review_send_second` or
`mapping.review_bulk_accept`.

The queue shows no personal data beyond the curriculum itself: no names of authors or reviewers.
