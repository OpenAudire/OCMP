# Exporting a curriculum version

On **Import and export**, at the bottom of the page, choose a curriculum version and download it in one of
three forms. You need permission to read reports and to view the curriculum; the files contain only what you
may see of the version (if you see only part, the file says so), and nothing is stored on the server. The design
is in [ADR 056](../adr/056-version-exports.md).

## The whole version as Excel (to edit and import back)

Phases, modules, sessions, objectives, tags and mappings in **the same sheets as the import templates**
([curriculum](importing-curriculum.md), [tags, mappings and frameworks](importing-tags-mappings-frameworks.md)).
Edit the cells you want to change and import the file back; importing an export into the version it came from
changes nothing until you edit something.

* Items you made on the screens have no External ID of your own, so the export writes their **internal id** in the
  External ID column and the import recognises it. **Do not change the External ID column** of an exported row: an
  import never renames an item's External ID, so a changed value is read as a new item.
* The **Status** column of the Mappings sheet only informs you; an import suggests the links (or accepts them if
  you say they were already reviewed).
* Rejected mapping links are not exported; retired objectives are. A faculty's own tag lists are not exported.
* It needs access to the whole version (a module coordinator gets the JSON and the matrix of their module, not
  this file).

## Objectives by framework items (Excel)

One row for each objective, one column for each item of the framework you choose (in the framework's order;
groups in italics). A cell holds the **coverage score (1 to 5) of the accepted link**, shaded by score; the end
of each row says how many items it covers and the bottom row how many objectives cover each item. Only accepted
links count, as in the [coverage reports](coverage-reports.md). The *About* sheet states the method, the
framework, the version and when it was made.

## The version as JSON

Everything you may see as one document: the version, phases, modules, sessions, objectives with their broader
objectives, assessments with their items, tags and mapping links with their source, status and accept method
(rejected links included). Items carry their internal id and their External ID. It is meant for other programs
and archives; it cannot be imported.

## Limits

At most 20 exports a minute for each person. Frameworks, users and the audit log are not part of these exports
(frameworks have their own pack format).
