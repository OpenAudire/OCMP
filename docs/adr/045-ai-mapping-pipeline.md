# ADR 045: The AI Mapping Pipeline

## Status

Accepted (Slice 1.16). Builds on ADR 016 (AI runs and links), ADR 039 (coverage and depth),
ADR 040 (review queue), ADR 042 (provider layer and privacy guard), ADR 043 (live links) and
ADR 044 (embeddings and the keyword fallback). Brief section 8, "Mapping pipeline".

## Context

Mapping a curriculum by hand is the slow part. The brief asks for an AI run that suggests links
and lands them in the review queue, with the rules that nothing is accepted automatically, the
privacy guard is never bypassed, every call is recorded, and the platform works without AI.
Slices 1.14 and 1.15 built the layer, the guard, the budgets and the embeddings; this slice uses
them for the first feature.

## Decision

### A run

A **run** maps the live, non-retired objectives of a **draft** version (the whole version, or one
module's outcomes and its sessions' objectives) to **one framework**. It is a row in `ai_runs`
(type `mapping`) with progress columns added in migration `0023`: `total_items`, `done_items`,
`failed_items`, `links_created`. `scope` holds the version, framework and module; `parameters` the
shortlist size; `prompt_version` is `mapping:1`.

`POST /curriculum-versions/{id}/ai-mapping-runs` checks everything that can be checked now (draft
version, usable framework, module in the version, shortlist size 3 to 20, objectives in scope, no
run of the same version and framework already queued or running, **AI switched on and allowed**)
and answers `202` with the run; a background job (`run_ai_mapping`) does the work. Refusals because
AI is off, restricted or not set up are `409` with the reason; the screen says so in words.
`GET /ai-mapping-runs/{id}` is polled for progress and `POST .../cancel` stops a run before its next
objective. Starting needs `ai.run` **and** `mapping.edit` at the programme, or at the module for a
run limited to it; module coordinators hold both at their module.

### The shortlist (`mapping_shortlist`)

The model is asked only about a short list, so the list decides what can be found. Each candidate
of the chosen framework gets a hybrid score:

| Signal | How | Weight with / without embeddings |
|---|---|---|
| Meaning | cosine of objective and item vectors, rescaled so that 0.75 counts as nothing and 0.95 as full (ADR 044: unrelated text of one subject scores in the high 0.7s and 0.8s) | 0.55 / 0 |
| Words | PostgreSQL full-text rank (`simple` configuration), scaled to the best hit | 0.30 / 0.80 |
| Precedent | the item was **accepted** for another objective with cosine 0.85 or more to this one | 0.15 / 0.20 |

Items **cross-referenced** from the best three come along with half of their source's score.
Items the objective is already linked to in any state, **rejected ones included**, are left out.
The top `k` (default 10) are sent. While embeddings are off or unreachable the list is made from
words alone (the notice from ADR 044), so the pipeline works without them, only less well.

### The prompt (`prompts.MAPPING`, version 1)

A code-owned `PromptTemplate` (ADR 042). Its fields are all on the allow-list: the framework's name,
the objective's level and text, the candidate lines (code, then title and description, cut at 500
characters each) and `mapping_examples` (a field added to the allow-list in this slice, as a reviewed
change). The system prompt carries no fields. The model must return JSON:
`candidates[]` of `code`, `is_match`, `coverage` (0 to 5, the scale of ADR 039), `depth_match`,
`confidence` (0 to 1), `rationale` (one sentence) and `evidence_quote`. The wording is versioned: any
change bumps `version`, runs record it, and the evaluation harness (Slice 1.19) compares versions.

**Few-shot examples.** When embeddings are on, up to four earlier reviewer decisions on objectives
with cosine 0.88 or more to this one (for this framework, accepted **and rejected**, most similar
first) are added to the prompt as "Earlier decisions by this institution's reviewers": the objective's
words, the item and whether it was accepted (with its coverage) or rejected. Rejections are how the
model learns what an institution does not count. Without embeddings there are no examples. They are
curriculum text and pass the same guard.

### Checking the answer (`ai/mapping_answer.py`)

The answer is untrusted text and is checked by a pure function: it must be JSON (a code fence is
tolerated) with a `candidates` list; only codes that were offered are accepted, each at most once; every
number is range-checked; a match needs a rationale and an `evidence_quote` that is **words of the
objective** (the rule `mapping.create_link` also enforces). **One retry**: if the answer is invalid the
call is made again with a note that lists what was wrong in fixed phrases. The model's own words are never
sent back or logged. An objective that fails twice is counted in `failed_items` and skipped. Each call is
marked `valid` or not, with the problems, on its `ai_run_calls` row.

### Saving and the guarantees

Matches with coverage 1 or more become links through `mapping.create_link`: source `ai`, status
**`suggested`**, naming the run, with coverage, depth, confidence, rationale and the evidence quote. A
non-match or a coverage of 0 makes no link. **A run never accepts anything and never creates a reviewed
state**: people decide in the review queue (ADR 040), and bulk accept keeps its own rules. The links
are attributed in the audit log to the person who started the run (`mapping.ai_suggest`).

### How a run ends

| State | When |
|---|---|
| `succeeded` | the loop finished; individual failures are counted, and personal-information skips are noted |
| `failed` | every objective that was asked about failed; or AI was turned off, restricted or lost its key meanwhile; or three provider failures in a row; or an unexpected error (a generic message, the cause is in the logs) |
| `budget_exceeded` | the monthly limit or the per-run call limit was reached (ADR 042); what was done stays |
| `cancelled` | a person cancelled; suggestions already made stay |

An objective whose text the privacy guard refuses (refuse mode) is **not sent**, is counted as failed
and noted ("some objectives were skipped because they may hold personal information"); the run goes on.
The job commits after each objective so the screen shows progress; it has **no automatic retries**
because a retry would call a paid provider again for work already done. A job that dies leaves the run
`running`; starting another run for the same version and framework is then refused until it is
cancelled (the cancel works on a `running` row).

### The screen

The mapping page shows **Suggest links with AI** to people who hold `ai.run` and `mapping.edit` on a
draft version. A dialog asks for the framework and the scope (the whole version, or one module);
the panel then shows the state in words, a progress bar, the numbers of objectives done, suggestions made
and failures, **Cancel run** while it goes on, and a link to the review queue when it made suggestions.
It polls every two seconds while a run is queued or running and refreshes the workspace and the review
count when it ends.

## Consequences

- Nothing AI-made counts until a person reviews it; reports (Slice 1.21) already have to show how a
  link was accepted.
- Cost is one call per objective that has candidates, plus the retry; the monthly limits and the
  per-run call limit of ADR 042 apply. A very large run can be limited by choosing one module.
- Quality is **not measured here**: the evaluation harness and the gold set are Slice 1.19. The weights,
  the floors in the shortlist and the number of examples are starting values chosen from the embedding
  measurements in ADR 044, not tuned on mapping decisions.
- A run reads the objectives as they are when it starts; an objective edited meanwhile is mapped as the
  job finds it.
- `ai_runs` rows are permanent (migration `0011`); `0023` only adds columns.
