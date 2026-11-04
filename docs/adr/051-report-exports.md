# ADR 051: Report Documents and Exports to Excel and PDF

## Status

Accepted (Slice 1.22). Builds on ADR 050 (the coverage and gap reports) and ADR 027 (what a user may
see). Brief, Phase 1 "Reports": "each viewable on screen and exportable to Excel and PDF; every
report states its method and date".

## Context

Committees and reviewers work in Excel and in PDF. A figure that leaves the application loses the
screen that explained it, so the file itself must say how it was made. The same report must also be
the same on screen and in the file, and the later reports (Slices 1.23 and 1.24) must not each
write their own exporter.

## Decision

### 1. A report is built once, as a document

`services/report_export.py` defines `ReportDoc`: a title, lines saying how it was made (the method
and its definition, the framework, the version, the time, the numbers used, what is counted, and
a warning when the person sees only part of the curriculum) and **sections**, each a table with
typed columns (text, integer, number, percent) and a sentence on how to read it. Builders in
`services/report_docs.py` turn the coverage and gap reports into documents; the screens, the
workbook and the PDF all read the same document.

`GET /curriculum-versions/{id}/reports/{key}` answers the document as JSON and
`.../reports/{key}/export?format=xlsx|pdf` as a file; `key` is `coverage` or `gaps` (1.23 and 1.24
register more in `report_docs.REPORTS`). The framework, method and phase come as query parameters.
Rules are those of the reports themselves: `reports.view` at the programme or at a module (then
the document says it covers only part of the curriculum), a version the user cannot see is a 404,
and a request that cannot be answered (no framework, a draft framework) is a plain 422.

### 2. Every sheet and every page states the method and the date

* **Excel**: an About sheet with every line, then one sheet per table. **Each sheet starts with the
  title, `Method: …` and `Made on: … UTC`.** Percentages are numbers with a percent format, columns
  are sized, the header row is frozen.
* **PDF** (A4 landscape): the title and the same lines, then the tables, with a header row that
  repeats on every page and **a footer on every page with the title, the method, the time and the
  page number**.

### 3. Untrusted text

Objective wording and module names are typed by people. In a workbook a cell starting with `=`, `+`,
`-`, `@`, a tab or a carriage return is written as **text** (otherwise a spreadsheet runs it as a
formula); in a PDF text is escaped for the paragraph markup and limited to what the built-in PDF font
can draw. File names are fixed (`coverage-report.xlsx`) and carry no user text. A table is cut at 20 000
rows; the gap report already caps its objective lists at 200 and says how many there are.

### 4. Dependency and limits

**reportlab** (BSD licence; it brings `pillow`) writes the PDF. The built-in Helvetica draws Western
European letters (so Afrikaans and the Latin letters of isiXhosa and isiZulu, with their accents) and
common punctuation; **other scripts become `?`**. Embedding a font would fix that and is not part of
this slice. **Labels in exports are English** whatever language the screen is in: the exports are not
translated yet. An export is limited to 20 a minute per person (a PDF costs CPU), and a request is
logged by user id, report and format only.

## What this does not do

* Charts, branding, a table of contents, or an evidence-pack layout (Phase 2).
* A scheduled or emailed report, or a stored copy: nothing is kept; a file is made when asked for.
* Translate the exports or embed a font for other scripts.
* Round-trip: an exported report cannot be imported (the round-trip exports are Slice 1.27).

## Consequences

* A new report is a builder that returns a `ReportDoc`; it gets screen data, Excel and PDF for free
  and cannot forget to state its method and date.
* The workbook and the PDF are tested by reading them back (sheets, stamps on every sheet and page,
  formula-looking text, markup and symbols).
