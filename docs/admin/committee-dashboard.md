# The committee dashboard

**Dashboard** in the menu gives a programme committee one page about one curriculum version: how far the mapping
has got, how well a framework is covered, where the gaps are and whether module credits and hours add up. You
need the permission to read reports and the curriculum for the programme (programme directors, the curriculum
office, deans and administrators). The design is in [ADR 058](../adr/058-committee-dashboard.md).

Choose the **version** (and, when more than one framework is in use, the **framework**) at the top. The choices
are kept in the address, so a link shows the same dashboard to someone else who may see it.

## The four indicators

Each card gives the figure, the counts behind it, how it moved over the last eight weeks **in words** (for
example "Up 20 points since 10 September") and a small trend line.

| Indicator | What it counts |
|---|---|
| **Objectives mapped** | Objectives with at least one **accepted** link of coverage 1 or more, out of the objectives you may see. Suggestions waiting for a decision do not count. |
| **Weighted coverage** | The headline of the *weighted content coverage* method for the framework (see [Coverage and gap reports](coverage-reports.md)). |
| **Framework items with no link** | Items with nothing below them that no accepted link reaches (the gaps list of the coverage report). |
| **Modules outside the credit tolerance** | Modules whose planned hours are under or over their credits × hours per credit by more than the tolerance (see [Assessments and credits](assessments-and-credits.md)). |

Everything is worked out like the reports, from what **you** may see. If you see only part of the version, the page
says so and shows no trend lines.

## Traceability

Pick a **programme outcome**. The diagram follows it down: the module outcomes linked beneath it, the session
objectives beneath those (counted, with their sessions) and the framework items their **accepted** links reach,
with the coverage (1 to 5) of the best link. An item at coverage 1 is shaded as weak. The sentence under the
diagram says the same in words. Session objectives linked straight to the programme outcome, without a module
outcome in between, are shown as their own group. Up to 12 items are shown, the ones reached by the most
objectives.

## Weighted coverage against the last published version

For each top-level group of the framework: the weighted coverage of this version and, as a pale bar behind it,
that of the latest other published version you may see. Groups under the institution's "low" share (coverage
setting, 40% by default) are marked **low** in words as well as colour.

## Mapping progress and credits

*Mapping progress by module* shows the share of each module's outcomes and session objectives with an accepted
link, and how many only have a suggestion waiting. *Credits and notional hours* is the credit check for every
module (credits, expected hours, planned hours, difference and status); tick **Only modules outside the
tolerance** to see just the ones to look at. The year totals are in the sentence above the table. The credit
check is advice and never blocks saving.

## Daily snapshots (for the trend lines)

The trend lines come from a daily record of the key figures of every draft and published version
(`metric_snapshots`: counts and shares only). The Docker Compose installation has a **`scheduler`** service that
records them when it starts and every 24 hours. To use another scheduler (cron, a systemd timer), run

```
docker compose exec api python -m app.cli snapshot-metrics
```

once a day. Running it again the same day replaces that day's row. Until the first snapshot there are no trend
lines and the page says so. The demo data comes with a **fictional** eight-week history so the lines show on a
fresh install; it is not a measure of anything.

## What it does not show yet

Declared versus delivered (needs the learning-management connector, Phase 2), the evidence-pack button
(Phase 2), trends across academic years and version differences (Phase 2).
