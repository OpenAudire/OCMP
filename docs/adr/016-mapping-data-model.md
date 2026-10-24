# ADR 016: Mapping, AI Run and Review Data Model

## Status

Accepted

## Context

The brief (sections 6–8) defines mapping links between objectives and framework items with
coverage (0–5), depth match, rationale, evidence quote, source, confidence and a review
status with first and second reviewers; AI runs that record provider, model, prompt version,
tokens, cost and timings, with prompts and responses kept for audit; review assignments;
an optional four-eyes mode where disagreements are flagged; and a rule that AI links are
never auto-accepted unless an admin enables a threshold, in which case they are marked as
AI-accepted in reports.

## Decision

### Tables
- `ai_runs`: type, status (queued, running, succeeded, failed, cancelled, budget exceeded),
  provider, model, prompt version, parameters and scope (JSON), token counts, estimated cost
  (USD), start and finish times, error.
- `ai_run_calls`: each provider request (as sent, after the privacy guard) and raw response,
  tokens, duration, whether it passed schema validation, error.
- **AI runs and calls are never deleted.** A database trigger refuses `DELETE` on both
  tables, `mapping_links.ai_run_id` is `RESTRICT`, and a check constraint requires every AI
  link to name its run, so every AI-made link stays traceable. Retention
  (`AI_CALL_RETENTION_DAYS`, default 365; `python -m app.cli purge-ai-content`) clears the
  stored prompt, response and error text and sets `content_purged_at`; tokens, timings,
  validity, the run record and its links remain. Database owners can still disable the
  trigger inside a maintenance transaction; the application cannot.
- `mapping_links`: **one row per (objective, framework item)**. Its status changes as people
  review it, and rejected rows stay as examples for later AI runs. Fields as in the brief,
  plus:
  - `accept_method` (individual, bulk, automatic, imported), set exactly when accepted, so
    reports can show AI-accepted (automatic) links separately;
  - `first_decision` and `needs_discussion`, to flag a second reviewer overturning the first;
  - `migrated_from_id`, the link a migrated link replaces (framework version migration).
  Check constraints: coverage 0–5, confidence 0–1, different first and second reviewers.
- `review_assignments`: reviewer, curriculum version, optional module (none = whole version),
  framework, stage (first or second), status, due date; unique per piece of work.

### Review workflow (`app/services/mapping.py`)
- AI and migrated links start `suggested`; hand-made links count as reviewed by their author;
  imported links arrive accepted (`imported`).
- A first reviewer accepts, rejects or sends to second review. In four-eyes mode an accept
  also goes to second review. By default a first-stage reject is final (rejecting adds no
  coverage); the institution setting `second_review_for_rejects` sends rejects to a second
  reviewer too.
- Policies live in `institutions.settings["mapping"]` (`four_eyes`,
  `second_review_for_rejects`, both off by default), read and validated by
  `mapping_policy_for()`; review functions take the policy as a parameter.
- The second reviewer must be someone else; a decision that overturns the first reviewer's
  accept or reject sets `needs_discussion`.
- A **rejected** link can be reopened (back to `suggested`) only by someone holding
  `mapping.review` at the objective's scope; reopening is recorded in the audit log
  (Slice 0.13). Accepted links are not reopened this way.
- Bulk accept applies one person's accept to suggestions at or above a confidence threshold
  (`bulk`).
- AI links must record their run and an evidence quote taken from the objective's own words
  (case and spacing ignored).
- Reviewers are `SET NULL` if their account is removed, keeping the decision.

### Choices
- *Revised 2026-10-25:* the first version allowed AI runs to be deleted (`SET NULL` on
  links) and kept the "AI links have a run" rule in the service only. Runs are now
  permanent and the rule is a database constraint; retention clears content instead.
  Reject-is-final became a default with a setting, and reopening was restricted to
  authorised reviewers and rejected links.
- `objective_scope()` gives the authorization scope of an objective (and so of its mappings
  and tags): session, module, or programme for programme outcomes.

## Consequences

- The AI pipeline, review queue UI and endpoints, automatic acceptance, coverage reports and
  framework migration are phase 1–2 work on these tables.
- Mapping changes will be recorded by the audit log (Slice 0.13).
