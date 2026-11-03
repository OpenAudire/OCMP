# ADR 046: AI Objective Rewrite and Classification

## Status

Accepted (Slice 1.17). Builds on ADR 033 (the rule-based quality checker), ADR 042 (provider
layer and privacy guard) and ADR 045 (the answer-checking approach of the mapping pipeline).
Brief section 5, "Objective quality checker": "Optional AI rewrite suggestion into a measurable
objective, shown as a diff the user can accept", and section 8, "classify domain and taxonomy
level".

## Context

The rule-based checker (ADR 033) tells a writer *what* is wrong with an objective ("vague verb:
understand") but not how to fix it, and it can only suggest a taxonomy level from a verb it
knows. Teachers asked for help with the fix. The platform must keep working without AI, an AI
suggestion must never change curriculum by itself, and the privacy guard applies to every call.

## Decision

### Two tasks, one interactive call each

Both tasks work on the wording **as the editor holds it**, so they work for an objective that is
not saved yet, and they are synchronous: a person is waiting a few seconds.

- **Rewrite**: a measurable version of the wording, with a one-sentence reason.
- **Classify**: a suggested domain (knowledge, skill, attitude) and taxonomy level, with a
  confidence and a one-sentence reason. Either may be `null` when the model is unsure.

Endpoints (one per kind of owner, like the quality checker):
`POST /curriculum-versions/{id}/outcome-ai`, `POST /modules/{id}/outcome-ai`,
`POST /learning-events/{id}/objective-ai`, with `{task, text, domain, taxonomy_level_id,
has_parent_links}`. They need `objectives.edit` at the scope that would own the objective (as
for adding one) **and** `ai.run` at the programme (programme outcomes) or the module (module
outcomes and session objectives). A person without `ai.run` does not see the buttons. AI off,
restricted, over budget or personal information found by the guard is a `409` with the reason;
a provider failure or an answer unusable twice is a `502`. Calls are limited to 20 a minute
per person.

### Nothing is saved and nothing is accepted

The result goes back to the screen. A rewrite is shown as a **word-by-word comparison**
(removed words struck through, added words underlined, and the words "Removed:" and "Added:"
for screen readers, so colour is never the only signal). **Use this wording** copies the
suggestion into the form; the objective is saved only when the person saves it, through the
ordinary update with its own permission checks, audit entry and "re-check mappings when the
wording changes" rule. **Use these** does the same for the domain and the level. Nothing is
stored about a suggestion except the call itself (below).

### What is sent

Only curriculum text, through two new prompts (`prompts.REWRITE`, `prompts.CLASSIFY`, version 1)
whose fields are on the privacy allow-list:

| Field | Content |
|---|---|
| `objective_text`, `objective_level` | the wording and its level |
| `quality_findings` (new, 2 000 characters) | the rule-based checker's findings as **fixed sentences** written in code ("The verb is vague and cannot be assessed."), never the user's words |
| `taxonomy_options` (new, 8 000 characters) | the configured taxonomy levels with their verbs, each with a short key (L1, L2, ...) |
| `answer_notes` (new, 1 000 characters) | fixed phrases naming what was wrong with an earlier answer, for the one retry |

The guard scans all of it as for every call; an objective with an email address or a phone number
is refused and nothing is sent. Levels are offered as keys so the model cannot invent one.

### Checking the answers (`ai/objective_answers.py`)

Pure functions, the same approach as ADR 045. A rewrite must be non-empty text of at most 600
characters and **must not add a number that is not in the original** (a made-up "80%" or "within
5 minutes" would invent a standard); it is marked *unchanged* when the model returned the
wording as it was. A classification must use a domain from the three words or `null`, a level key
that was offered or `null`, and a confidence from 0 to 1. Both need a rationale. Problems are
fixed phrases that never repeat the model's words. An invalid or cut-off answer is retried once
with those phrases; a second failure is a `502`. A call that fails with a "try later" status is
made again once after 1.5 seconds.

### Records

One `AIRun` per request (type `rewrite` or `classification`) holds its calls, tokens and cost, so
budgets and the call record of ADR 042 apply unchanged. A run that is refused by the guard is
recorded as failed.

## Consequences

- A suggestion can be wrong or change the meaning. The comparison makes that visible; the number
  check stops one kind of invention, but **the quality of the rewrites is not measured** (the
  evaluation harness in 1.19 covers mapping only). Teachers must read the comparison.
- An accepted AI wording is not marked as AI-written in the data. If reports or audits need to
  know, the suggestion would have to be carried to the save (a later decision).
- The prompt asks to keep the language of the original. Whether the model does this well for
  Afrikaans, isiXhosa and isiZulu has not been tested.
- Each press of a button is one paid call (about 1 000 input and 100 output tokens); the monthly
  budget and the per-minute limit apply.
