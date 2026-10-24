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
  tokens, duration, whether it passed schema validation, error. Retention policies can purge
  these while keeping the run summary.
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
  also goes to second review. A first-stage reject is final in both modes (rejecting adds no
  coverage).
- The second reviewer must be someone else; a decision that overturns the first reviewer's
  accept or reject sets `needs_discussion`.
- Decided links can be reopened. Bulk accept applies one person's accept to suggestions at
  or above a confidence threshold (`bulk`).
- AI links must record their run and an evidence quote taken from the objective's own words
  (case and spacing ignored).
- Reviewers are `SET NULL` if their account is removed, keeping the decision.

### Choices
- The "AI links have a run" rule is in the service, not a check constraint: deleting a run
  (`SET NULL`) must not be blocked.
- `objective_scope()` gives the authorization scope of an objective (and so of its mappings
  and tags): session, module, or programme for programme outcomes.

## Consequences

- The AI pipeline, review queue UI and endpoints, automatic acceptance, coverage reports and
  framework migration are phase 1–2 work on these tables.
- Mapping changes will be recorded by the audit log (Slice 0.13).
