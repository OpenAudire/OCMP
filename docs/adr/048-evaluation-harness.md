# ADR 048: Evaluation Harness and Gold Sets

## Status

Accepted (Slice 1.19). Builds on ADR 045 (the mapping pipeline whose quality it measures) and
ADR 040 (bulk accept, whose floor it helps to choose). Brief section 8, "Quality and cost": "Eval
harness: compares AI suggestions with a human-mapped gold set; reports precision, recall and
Cohen's kappa, per prompt version and model. Ship a fictional gold set for the demo data."
Phase 1 "definition of done": the harness runs on a fictional gold set and reports Cohen's kappa
(target for the real pilot: kappa of at least 0.6 between AI and human mappers).

## Context

Slices 1.16 to 1.18 chose several numbers without evidence: the minimum coverage of an AI
suggestion (`ai_min_coverage`, default 1), the bulk-accept floor (`bulk_accept_min_percent`,
default 80) and the shortlist weights. The first real run (Slice 1.16b) showed that mocked
tests do not find real problems. We need a way to mark the AI against an answer key written by
people, to compare prompt versions and models, and to choose those numbers from evidence.

## Decision

### 1. A gold set is data people write; Excel is the way in

A **gold set** is a list of objectives, each with the framework items a person decided it maps
to (coverage 0 to 5 and depth). It is filled in by hand in an Excel workbook and imported. The
workbook (`Gold set` sheet) has one row for each objective and framework item with the columns
**Objective text, Framework item code, Coverage (0-5), Depth, Notes**. An objective that maps to
nothing has one row with no code. A coverage of 0 means "I looked and it does not map here".
The template carries dropdowns (coverage 0 to 5, the four depth values, and the framework's
item codes) and an instruction sheet, and no example rows (they would be imported by mistake).
Notes are never read.

Import checks the whole file and reports **every problem with its row number** before anything is
saved (a `dry_run` option answers without saving). Codes are checked against the framework, case
ignored. The same workbook is the export of a saved gold set, so a set can be edited and imported
again. Objectives are identified by their **wording** (spaces and case ignored), not by an id,
so a set made by hand needs no ids.

This adds one dependency, **openpyxl** (MIT), to read and write the workbooks. The brief already
requires Excel templates and exports; this is the first slice to need them, and the same library
will serve the later ones. Files are limited to 5 MB and 5 000 rows, are read in memory and are
never stored.

### 2. A run asks the AI and saves nothing

An **evaluation run** reuses the mapping pipeline unchanged: the same shortlist, the same prompt
(`mapping:2`), the same answer checks and one retry, the same budget limits. It differs in three
ways, all so the measurement is clean:

* **No link and no objective changes.** The answers are kept on the run (`eval_runs.results`).
* **A cold start.** The shortlist ignores links the objective already has and the precedent boost
  from earlier accepted links, and the prompt carries no examples of earlier reviewer decisions
  (`include_linked=True`, `use_precedent=False`). Otherwise the AI's own earlier accepted
  suggestions, or the demo data's hand-made links, would make the figures look better than they
  are. The consequence is that the figures are conservative for a programme with reviewed links.
* **Objectives are found in a curriculum version by wording**, because the shortlist needs the
  objective's stored vector. A gold objective the version does not have is counted as not found
  and left out of the figures. Gold sets that are not in the version (a real gold set made from
  last year's wording) therefore show up at once.

A run is an `ai_runs` row of the new type `evaluation` (so its calls, tokens and cost are
recorded and limited like any other) plus an `eval_runs` row. A background job does the work and
commits after each objective; there are no automatic retries of the job (a retry would pay
again). One evaluation of a gold set at a time. Needs `settings.manage`.

### 3. The figures are worked out from stored answers, at any threshold

Because the raw answers are kept, **precision, recall, F1 and Cohen's kappa are worked out
afterwards** (`services/eval_metrics.py`, pure functions) at any minimum coverage and any
bulk-accept floor, without calling the AI again. Definitions:

* For each objective the **universe** is every item the AI was shown (its shortlist) plus every
  item the gold set or the AI named.
* An item is **gold-positive** when its gold row has coverage 1 or more, and **AI-positive** when
  the AI suggested it at the chosen minimum coverage (and, with `ai_prefer_specific_item`, not
  dropped for a more specific child).
* True positive: both yes. False positive: only the AI. False negative: only the gold set (this
  includes items the shortlist never showed, which is a retrieval failure, not a model failure).
  True negative: neither.
* **Precision** = TP / (TP + FP). **Recall** = TP / (TP + FN). **Kappa** compares the two yes/no
  answers over the whole universe.
* **Shortlist recall** (the share of gold links that were shown to the AI at all) is reported
  next to recall because it is the ceiling for recall and tells retrieval problems from model
  problems.
* On agreed links: the mean gap in coverage, the share within one point, and the share where
  the gold depth (when given) matches.
* Objectives the AI could not answer (invalid answer twice, provider failure) are **left out of
  the figures and counted separately**; they are not counted as wrong.

**Kappa depends on the shortlist length**: a longer shortlist adds true negatives and raises
kappa without the AI getting better. The figures always show the average number of items shown,
and kappa is compared only between runs with the same shortlist size. This is a property of
Cohen's kappa on a retrieval-then-judge pipeline, not something to hide. The README of the
harness says so and the page repeats it.

**Bulk accept**: for each floor from 50% to 100% the harness reports how many suggestions would
be accepted in bulk, how many of those are right and wrong, the precision of the accepted set,
and how many are left for review. The floor is chosen by the lowest precision the institution
accepts for links nobody looks at.

### 4. Where it lives

* `app/models/evaluation.py`: `GoldSet`, `GoldCase`, `GoldLink` (audited, curriculum wording and
  codes only) and `EvalRun` (derived data, not audited, not exported). Migration `0026`.
* `app/services/eval_gold.py` (Excel and JSON in and out), `eval_run.py` (the run),
  `eval_metrics.py` (the figures); `jobs/evaluation.py`; `api/v1/ai_evaluation.py`.
* CLI: `eval-template`, `eval-import`, `eval-run`, `eval-report` (`scripts/eval_mapping.py`
  stays as a thin pointer to them).
* Admin page `/admin/ai-evaluation` (needs `settings.manage`): gold sets, running, and a
  comparison table of runs by prompt version and model at a chosen minimum coverage, with the
  sweep by minimum coverage, the bulk-accept table and the objectives where AI and gold set
  disagree.

### 5. The demo gold set is fictional and says so

`backend/app/demo/data/gold-set-demo.json` marks the 60 objectives of the demo programme against
the 8-item Demo Graduate Competencies framework. It was **written by the developers, one
person's judgement, not by a panel**; it is flagged `is_demo`, shown as "Fictional demo", and
its figures measure nothing about real quality. A test fails if the demo data and the gold set
drift apart. (For what it is worth: on the 12 module outcomes that the demo data maps itself, the
gold set agrees on 10 of 12 objectives, which shows that two people already disagree on a small
fictional framework.)

## What this does not do

* It does not choose the defaults. It supplies the evidence; changing `ai_min_coverage` or
  `bulk_accept_min_percent` is the owner's decision, from a **real** gold set.
* It does not compare models in one click. A run uses the model configured at the time; to
  compare models, change the model in the AI settings and run again. The page lists the runs by
  prompt version and model.
* It does not measure rewrite, classification or study-guide extraction (mapping only).
* It does not measure the shortlist weights separately (shortlist recall is the nearest figure).
* Gold sets in other languages are not tried.

## Consequences

* A new Excel-reading dependency and a new file-upload surface (5 MB, in memory, never stored).
* Every prompt or model change can be marked before it ships, and the answer key outlives the
  prompts.
* A gold set holds curriculum wording. It is covered by the same privacy guard as any AI call:
  an objective the guard refuses is counted as not answered.
