# Redundancy and traceability reports

Two reports about the curriculum itself, not about one framework's coverage. Open **Reports** in the menu.
Like every report they state their method and the time they were made, can be downloaded as Excel or PDF
([Coverage and gap reports](coverage-reports.md#exporting-a-report)), need the `reports.view` permission and
show only what you may see. The design is in [ADR 052](../adr/052-redundancy-and-traceability.md).

## Taught in many sessions

(The key `redundancy`; it used to be called the redundancy report. Many sessions is not wrong in itself.)

Choose a version and a framework.

**Items taught in many sessions.** For each framework item, how many *sessions* have an objective that is
**accepted** for it (and in how many modules). An item is listed when that number is at least the larger of
**4** and, once five or more items are taught, the **average plus 1.5 standard deviations**. The report prints
the threshold it used. The two numbers are institution settings (`repeat_min_sessions` and `repeat_spread` in the
`coverage` section, see [Basics](basics.md)); the starting values have not been measured on a real programme. A long list is not a verdict: an item taught in many sessions can be a deliberate thread. It is
a list of places to look.

**Marked as intentional (spiral curriculum).** A programme that returns to a competency on purpose can say so:
below the report, choose the item, give a reason (optional) and press *Mark as intentional*. It needs the
`curriculum.edit` permission at the programme (a programme coordinator or director). The item then leaves the
list and appears in this table with its reason; *Remove mark* lists it again. Marks belong to the programme (all
its versions) and are recorded in the audit log. Everyone who can see the report sees the marks.

**Near-duplicate objectives in different modules.** Pairs of objectives of the same level, in different
modules, whose wording is close (the same threshold as the objective checker, 95% unless your institution
changed it), most similar first. This needs the [embeddings service](../operations/embeddings.md) and a run
of `embed-all`; without them the table is empty.

## Traceability report

Choose a version; a framework is optional (without one, every framework's items are shown with the
framework's name).

* **From programme outcome to framework item.** Each row is one path down the upward links: a programme
  outcome, the module outcome linked up to it, the session objective linked up to that, the session, and
  the framework items the last objective is accepted for. A session objective linked straight to a
  programme outcome has its own row. A programme outcome with nothing below it says so.
* **Not linked upward to a programme outcome you can see.** Module outcomes and session objectives no
  programme outcome reaches. These are the gaps in traceability. Objectives made from a
  [study guide](users-and-roles.md#study-guides) start here until someone links them.

If you do not see the whole curriculum (a module coordinator, a lecturer) you do not see the programme
outcomes; the report says it covers only part of the curriculum.

## Limits

The words in the tables (headings, notes) are English for now, in the screen, the Excel file and the PDF.
