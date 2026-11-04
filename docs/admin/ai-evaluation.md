# Checking the AI's mapping

Before you trust the AI's mapping suggestions, mark them against an answer key that people wrote, and
use the result to choose two settings: the **minimum coverage** of a suggestion and the **bulk-accept
floor**. This page shows how. It needs the `settings.manage` permission (the people who set up
[AI](ai.md)). The design is in [ADR 048](../adr/048-evaluation-harness.md).

## What you need

* AI turned on and a provider chosen ([AI settings](ai.md)). A run calls the provider and **costs
  money**, a few cents for sixty objectives; the cost is shown with the result and counts against the
  [budget](ai.md#budget).
* A **gold set**: a list of objectives with the framework items a person decided they map to.
* The objectives of the gold set in a curriculum version, with the **same wording** (the AI is
  asked about the objectives as they are stored).
* Optional but wanted: [embeddings](../operations/embeddings.md) on, as in daily use, so the
  shortlist is the one your users get.

## Make a gold set

1. On **Admin > Check the AI's mapping**, choose the framework and download **the Excel template**
   (or `python -m app.cli eval-template --framework "<name>" --out gold-set-template.xlsx`).
2. Fill in the `Gold set` sheet, one row for each objective and framework item:

| Column | What to write |
|---|---|
| Objective text | The objective's wording, copied exactly from the curriculum. The same wording on several rows is one objective |
| Framework item code | A code of the framework (a dropdown lists them; the `Framework items` sheet shows their titles) |
| Coverage (0-5) | How much of this one item this one objective covers, on the scale reviewers and the AI use: 0 = it does not map here, 1 = 1 to 20%, 2 = 21 to 40%, 3 = 41 to 60%, 4 = 61 to 80%, 5 = 81 to 100% |
| Depth | `below`, `matches`, `above`, or `not_applicable` (the item has no verb or level). Leave blank if unsure |
| Notes | For yourself. The program never reads this column |

   An objective that maps to **nothing** in the framework gets one row with only the objective text.
   Do not leave such objectives out: the AI is also marked on whether it suggests links that do not
   exist.
3. **Decide the answers without looking at the AI's suggestions.** Better still, have two people
   fill in the same objectives separately and settle the differences: the figures below only say
   how well the AI agrees with the answer key, and a key one person wrote is that person's view.
   Sixty to a hundred objectives, taken from several modules, is a useful size.
4. Do not put the names of people or patients in any cell.

## Add it

On the same page, under **Add a gold set**, give it a name, choose the framework and the file, and press
**Check the file**. Every problem is listed with its row number (a coverage that is not 0 to 5, a
depth that is not one of the four words, a code the framework does not have, a repeated row). Nothing is
saved until the file is sound; then press **Save the gold set**. From the command line:

```bash
docker compose cp gold.xlsx api:/tmp/gold.xlsx
docker compose exec -T api python -m app.cli eval-import /tmp/gold.xlsx \
    --name "Pilot gold set" --framework "My framework" --dry-run
```

(The commands run inside the `api` container, so a file on your machine has to be copied in first. The
page uploads the file for you and needs none of this.)

Drop `--dry-run` to save. A saved gold set can be downloaded again in the same layout, edited and
imported under a new name. The fictional **demo gold set** (60 objectives of the demo programme, written
by the developers) is loaded with `python -m app.cli eval-import --demo`; it shows how the page works and
measures nothing about real quality.

## Run an evaluation

Choose the gold set and the curriculum version that holds its objectives and press **Run the
evaluation**. The AI is asked about each objective exactly as in a [mapping run](mapping.md), with
the same shortlist, prompt and checks, but **nothing is saved**: no link is made and no objective
changes. Two things are switched off so that earlier decisions cannot flatter the result: the
shortlist ignores links the objective already has, and the AI is not shown examples of earlier
reviewers' decisions. A programme with reviewed links will do somewhat better than the figures say.

A run takes a few minutes. The page shows progress and a **Cancel** button. Command line:

```bash
docker compose exec -T api python -m app.cli eval-run \
    --gold-set "Pilot gold set" --version <curriculum version id> --email you@example.org
```

Gold objectives that the version does not have (the wording differs) are listed as *not found* and
left out of the figures. Objectives the AI could not answer are counted separately and are not counted
as wrong.

## Read the figures

Each row of **Results** is one prompt version and model on one gold set; add a row by running again after
changing the prompt (a new release) or the model ([AI settings](ai.md)).

| Figure | Meaning |
|---|---|
| **Precision** | Of the links the AI suggested, the share the gold set also has. Low precision means reviewers spend time rejecting |
| **Recall** | Of the links in the gold set, the share the AI suggested. Low recall means gaps the AI never raises |
| **F1** | One number from the two (their harmonic mean) |
| **Link kappa** (kappa) | Agreement between the AI and the gold set, beyond chance, on **which links exist**. 0.6 is the target for the real pilot (brief, section 8); 0 is no better than chance |
| **Coverage-score kappa** | Agreement on the **coverage score** (0 to 5) between the AI and the gold set, on the links **both** made, as plain Cohen's kappa (any difference counts the same). Theurich et al. 2025 report this kind of kappa (0.68) between their two human raters, so it is the one to compare with that. It is worked out on a different set (links both made) from the link kappa and says nothing about which links exist; the page shows how many links it rests on. Beside it, the **weighted kappa** (quadratic weights, near misses count for little) is an extra: it reads higher and is not comparable with the published figure |
| **Shown to the AI** | The share of gold links that were on the AI's shortlist at all. Recall can never be higher than this, so a low figure points at retrieval (embeddings, shortlist size), not at the model |

!!! warning "Kappa depends on the shortlist"
    Kappa counts every item the AI was shown that nobody linked as an agreement. A longer shortlist
    adds easy agreements and raises kappa without the AI getting better. Compare kappa only between runs
    that show about the same number of items (the page states the average), and look at precision and
    recall first.

Under a run you also get **the objectives where the AI and the gold set disagree**, with the items each
side named and which ones the AI never saw. Read these: they show whether the answer key or the AI is
wrong, and a wrong key is common.

## Choose the two settings from the figures

**Minimum coverage** (`ai_min_coverage` in the mapping settings, 1 to 5). Change *Count suggestions with a
coverage of* and read how precision and recall move; the table shows every value at once and costs
nothing, since the figures are worked out from the stored answers. Take the highest minimum whose recall
you can live with, or the lowest whose precision your reviewers can.

**Bulk-accept floor** (`bulk_accept_min_percent`, 50 to 100). The second table shows, for each floor, how
many suggestions would be accepted in bulk, how many of those are **wrong**, and how many are left for
review. Bulk-accepted links are accepted without a person reading them, so pick the lowest floor at which
the accepted links are right as often as you require (a floor with no wrong links in a sample of sixty
says little: it needs a larger gold set to be trusted). Bulk-accepted links stay marked as such in
reports.

None of this is changed for you. The settings are yours to change once the figures come from a gold set
people wrote.

## What the figures do not cover

* Mapping only: rewrite, classification and study-guide extraction are not marked.
* Languages other than English are not tried.
* The shortlist's own weights are not tuned here; "Shown to the AI" is the nearest measure.
* One model at a time: to compare two models, change the model in the AI settings and run again.
