# Importing the curriculum from Excel

Build or update a **draft** curriculum version from a spreadsheet: phases, modules, sessions and
objectives. Open **Import and export** in the menu. You need permission to edit the curriculum and its
objectives for the programme (a programme director or the curriculum office). The design is in
[ADR 054](../adr/054-curriculum-excel-import.md).

## The steps

1. Choose the draft version and **download the Excel template**. It has one sheet each for Phases,
   Modules, Sessions and Objectives, an **Instructions** sheet that explains every column, and a **Lists**
   sheet with the dropdown values (your teaching formats and taxonomy levels). Required columns have a dark
   heading. Hover a heading for its help.
2. Fill in the sheets you need. Leave the others empty. Do not put the names of people or patients in any cell.
3. Choose the file and press **Check the file**. Nothing is changed. You see either the **problems** (sheet, row,
   column and what is wrong) or **what would happen** to every row: new, updated (and which fields) or unchanged.
4. Fix problems in the spreadsheet and check again. When the preview is right, press **Import into the
   curriculum**. The check is valid for 30 minutes; the file is checked once more when you confirm.

If the file has any problem, **nothing** is imported.

## External ID: how importing again works

Every row has an **External ID**: your own identifier (a code from your student system, or any text that is
unique in its sheet). Importing a row whose External ID is already in the version **updates** that item; a new
External ID **creates** a new item. So you can correct the spreadsheet and import it again without making
duplicates. When you copy a version forward, the External IDs go with it, so next year's file updates next
year's draft.

Other sheets refer to rows by External ID: a module names its phase, a session its module, an objective its
module or session, and an objective's *Broader objectives* name the objectives it contributes to (separate
several with a semicolon). An External ID can refer to a row in the same file or to an item already in the
version that has that External ID.

## What an import does and does not do

* A **module made on the screens** has no External ID yet. A row whose Code matches such a module adopts it: the
  module is updated and gets the row's External ID (the preview says "External ID" among the changes). Phases,
  sessions and objectives made on the screens have no such natural key and cannot be matched: importing them
  would create new ones, so use the import for them from the start (or leave them out of the file).
* It **never deletes** anything, and never moves a session to another module or changes an objective's level or
  owner (it reports that as a problem; change those on the screens).
* A column you remove from a sheet is **left alone**. A column that is there but blank **clears** the value
  (a module with a blank Phase becomes longitudinal). *Broader objectives* only adds links.
* New objectives are saved as **draft**. Changing the wording of an existing objective follows the usual rules:
  it goes back to *ready for review* unless you may approve objectives.
* Everything goes through the same rules as the screens (unique module codes, links to the right broader
  objectives) and every change is recorded in the audit log. Each import is also recorded as an import job
  (counts only: never the file or its name).
* Only draft versions can be imported into.

## Limits

The file may be as large as the installation's upload limit (`PACK_MAX_UPLOAD_MB`, 10 MB by default) and has
at most 5 000 rows a sheet. The template's headings and instructions are English for now. Tags, mappings and
frameworks, and the import history, are in [Importing tags, mappings and frameworks](importing-tags-mappings-frameworks.md).
