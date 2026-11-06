# ADR 058: The Committee Dashboard and Its Daily Snapshots

## Status

Accepted (Slice 1.28). Builds on ADR 027 (what a person may see), 035 (credits), 050 (coverage) and the
traceability report of ADR 052.

## Context

The brief asks for a basic committee dashboard: mapping progress, a coverage summary, top gaps and credit
warnings. The approved mockup adds trend lines over eight weeks, a traceability diagram from a programme
outcome to the framework, coverage against the last published version, mapping progress by module and the
credits table. Trends need history, and the installation has no scheduler.

## Decision

**One screen, one request.** `GET /curriculum-versions/{id}/dashboard` (and `.../dashboard/traceability` for
the diagram) need `reports.view` at the programme, or at a module of it for a narrower view. A version the
person cannot see is a 404. Everything is worked out for **what the person may see** (ADR 027) with the
same functions as the reports (`search.visible_objective_ids`, `coverage_report.build_report`,
`credit_check.version_credit_check`), so the dashboard can never disagree with a report.

**Four indicators**, each with its figure, the counts behind it and a trend line:

1. *Objectives mapped*: objectives with an accepted link of coverage 1 or more, as a share of those the
   person sees.
2. *Weighted coverage* of one framework (the weighted method of ADR 050, its headline).
3. *Framework items with no link*: items with nothing below them and no accepted link.
4. *Modules outside the credit tolerance*: planned hours under or over credits x hours per credit.

The framework is the one with the most links from this version unless the person picks another.

**Daily snapshots.** `metric_snapshots` holds one row for each version and day with the same figures for the
**whole** version (counts and shares only: no text, no names). `snapshot-metrics` (CLI) writes today's row for
every draft and published version; the same day again replaces it. The Docker Compose file has a `scheduler`
service (`run-scheduler`) that runs it at start and then daily at 23:55 in `TIMEZONE` (default
Africa/Johannesburg, set by the owner in Slice 1.31; a "day" is a local day), so installs get snapshots with no cron; any other
scheduler can run the same command. Snapshots are derived data: not audited, not exported, and they go with
the version.

**Trend lines only for the whole version.** A snapshot is of the whole version, so a person who sees only
part of it (ADR 027) gets today's figures for their part and **no trend**, and the page says so. The line is a
picture of numbers that are also written out (the figure, the change in words, an `aria-label` with the first
and last value).

**Coverage against the last published version.** The other published version of the programme with the
highest academic year that the person may see; the groups at the top of the framework are compared by their
weighted value. Groups under the institution's "low" share are marked with a word as well as a colour.

**Traceability.** From one programme outcome: the module outcomes linked beneath it, the session objectives
beneath those (counted, with their sessions), and the framework items their accepted links reach (at most 12,
the ones reached by the most objectives, then a count). Session objectives linked straight to the programme
outcome and to no module outcome under it are shown as their own group. The diagram is HTML text nodes on a
grid with SVG curves behind them (decoration, `aria-hidden`), and the summary under it says the same in words.

**Demo data.** `load-demo` seeds a **fictional** eight-week history for the demo versions, rising towards the
real figures, so the trend lines show on a fresh install. It is marked as demo data in the documentation and
is never written for real data.

## Not in this slice

* Declared versus delivered and the evidence-pack button (Phase 2, Phase 1 decision 2).
* Trends across academic years and version diffs on the dashboard (Phase 2).
* A choice of other indicators, or alerts when an indicator moves.

## Consequences

* One more table and one more service in the Compose file. An install without the `scheduler` (or another
  scheduler) simply has no trend lines until someone runs `snapshot-metrics`; the page says so.
* The dashboard is as slow as the coverage report of the chosen framework plus a credit check (it runs the
  weighted coverage twice when a previous version exists). It is not cached; if that becomes a problem the
  snapshot already holds the current figures.
