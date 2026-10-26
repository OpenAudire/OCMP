# Assessments and credits

Each module can list its assessments and the items in them, and say which objectives each
item assesses. The builder also checks the credits of every module against its planned
learning hours, and the credits of every year and NQF level. The design is in
[ADR 035](../adr/035-assessments-and-credit-check.md).

## Assessments

Open a draft version in the curriculum builder, select a module and find **Assessments**
under its outcomes. People with `curriculum.edit` for the module (module coordinators,
programme directors, the curriculum office) can:

- **Add assessment**: a name, a **method** (from your assessment-method tag lists, see
  [Tag lists and tagging](tag-lists.md)), a **weight** (percent of the module mark), the
  **timing** in words ("Week 8"), and the **time in the assessment** in minutes.
- **Add item** to an assessment: a label ("Question 1", "Station 3"), the marks, and the
  **objectives it assesses**. The choices are the outcomes of the module and the objectives of
  its sessions. Programme outcomes are reached through the upward links of those objectives.
- Edit or delete an assessment or an item. Deleting an assessment deletes its items; every
  change is recorded in the change history.

Lecturers can read the assessments of their modules but not change them. Published and
archived versions are read-only. Copying a module or phase copies its assessments, items and
links to the copied objectives. Copying a year forward does the same and keeps the link to
the original, so **Compare** lists added, removed and changed assessments. A method that
assessments use cannot be deleted from the tag list; make it inactive instead.

The weights of a module's assessments should add up to 100%. The module says so when they do
not; it never stops you saving.

## Credits and notional hours

All of this is advice. Nothing is refused because of it.

**Per module.** The planned hours are the contact time and the self-study of the module's
sessions plus the time in its assessments. The expected hours are the credits times the hours
per credit (10 by default). The module shows, in words and with an icon, whether the planned
hours fit, are under or are over the expected hours. A difference up to the tolerance (10% by
default) fits.

**Per version.** **Check credits** in the version bar opens **Credits and hours**:

- The total credits, against the programme's total credits and the minimum of its
  qualification type.
- Credits per year: every phase of kind *year* is compared with the typical credits per year
  (120 by default). Blocks and other phases, and modules that run across phases, are only
  totalled.
- Credits per NQF level, and a note for modules above the programme's NQF exit level. Set
  `min_exit_level_credits` to also check the credits at the exit level.
- Every module with its planned and expected hours and the check.

The qualification types and their credit minimums are seeded values to verify against the
current CHE and HEQSF documents; the page reminds readers of this.

The demo programme has only a few sessions per module, so it shows the hours as *under*.

## Changing the figures

The figures are the `credits` section of the institution settings (platform admin, through the
API, see [Admin basics](basics.md)):

| Setting | Default | Meaning |
|---|---|---|
| `hours_per_credit` | 10 | Notional hours of one credit |
| `tolerance_percent` | 10 | How far the planned hours may differ from the expected hours |
| `credits_per_year` | 120 | Typical credits of a year |
| `min_exit_level_credits` | off | Credits wanted at the programme's NQF exit level |

```bash
api -X PATCH "$SITE/api/v1/institution/settings" -d '{
  "credits": {"hours_per_credit": 10, "tolerance_percent": 10, "credits_per_year": 120}
}'
```
