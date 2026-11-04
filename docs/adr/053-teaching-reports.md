# ADR 053: Teaching Reports

## Status

Accepted (Slice 1.24). Builds on ADR 051 (report documents and exports), ADR 035 (assessments, credits
and notional hours), ADR 034 (tag lists) and ADR 027 (what a user may see). Brief, Phase 1 "Reports":
teaching formats and contact hours, the curriculum relationship report (One45-style), the role balance
report (health profile) and assessment methods coverage.

## Context

The coverage reports look at the framework. These four look at how the curriculum is taught and assessed.
The brief names them without defining the figures, so each figure is stated here and printed on the report.

## Decision

All four are builders of `ReportDoc` (ADR 051) in `services/report_docs_teaching.py`, registered in
`report_registry.REPORTS`. They get the screen, Excel, PDF, access rules and "partial view" notice of
every report. Hours are minutes divided by 60, to one decimal.

1. **Teaching formats and contact hours** (`formats`, no framework). Sessions, contact hours and self-study
   hours by teaching format (the session's teaching-method tag; none is "No format set") with each format's
   share of contact time, by phase and format (with the phase total), and by module. An optional `phase_id`
   limits it to one phase. The figures are the *planned* minutes of the sessions; they are not compared with
   the credits (that is the credit check, ADR 035).
2. **Curriculum relationship** (`relationship`, no framework). One row for each session and each objective of
   that session (a session with no objective has one row): phase, module, week, session, format, the tags of
   the session and the tags of the objective. A table to filter in Excel; cut at 5 000 rows.
3. **Role balance** (`role-balance`, framework required, health profile only). For each phase and each
   top-level group of the framework: the contact hours and the share of the phase's contact time, and the
   number and share of the phase's objectives. **Corrected in Slice 1.24a:** each *objective* of a session
   gets an **equal share of the session's contact time** (minutes divided by the number of its objectives),
   and that share is divided equally among the distinct top-level groups the objective is *accepted* for
   (not an equal split per group, as first built). An objective whose own accepted links give no group is
   **estimated**: first from the accepted links of the module outcomes it links up to (`ObjectiveLink`);
   only if it has **no** upward link, from the accepted links of all outcomes of its module (a session with
   no objective at all is estimated the same way). Upward links whose outcomes are unmapped leave the
   objective "not mapped", not the module's groups. Estimated hours and objectives are shown in their own
   column ("of which estimated"). The rules are pure functions in `services/role_balance.py`. An objective
   that maps to two groups counts for both in the objective counts, so those shares can exceed 100%. The
   report is refused (422) while the institution's profile does not include the `role_balance_report`
   feature, and the screen hides it.
4. **Assessment methods** (`assessments`, no framework). For every value of the assessment-method tag lists:
   the number of assessments, the modules they belong to, the objectives their items assess, and the modules
   and objectives tagged with the method. A second table lists the module outcomes and session objectives
   that no assessment item is linked to and that have no assessment-method tag (200 shown, with the total).
   It is a basic view; blueprints and weighting come later.

## What this does not do

* Judge whether a mix of formats is good, or compare hours with credits.
* Split a session's time by how much of it each objective actually takes (equal shares per objective are a
  stated simplification; sessions have no such figure).
* Count time of sessions the reader cannot see.
* Translate the tables (ADR 051). The phase filter is in the API; the screen does not offer it yet.

## Consequences

* Four builders and four registry entries; the generic report screen (Slice 1.23) shows them.
* Equal shares per objective remain an assumption (sessions have no time per objective); estimated figures are labelled.
