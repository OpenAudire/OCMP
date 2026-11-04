# Importing tags, mappings and frameworks from Excel

Three more imports on **Import and export**, built like the [curriculum import](importing-curriculum.md): a
template made from the same field definitions that check your file, a **check that changes nothing**, the plan
row by row, and a confirmation. If the file has any problem, nothing is imported. The design is in
[ADR 055](../adr/055-excel-imports-tags-frameworks-mappings.md).

## Tags (needs permission to manage tag lists)

Download the template: a **Tag lists** sheet (list key, name, kind, description, applies to) and a **Tag values**
sheet (list key, label, code, description). A list is matched by its **key** and a tag by its **label**, so
importing again updates instead of duplicating. Nothing is deleted or deactivated; the kind of an existing list
cannot change; a faculty's own lists are managed on the Tag lists screen, not here. This imports lists and
tags; applying a tag to modules, sessions or objectives is done on their screens.

## Mappings (needs permission to edit mappings; draft versions)

Choose the draft version and download the template. Each row names an objective by its **External ID** (set by
the curriculum import), the framework by its **key** (its active version, or the *Framework version* you
give), the item's **code**, the **coverage** (1 to 5, the same percentage bands as in the mapping screen), the
depth (blank means *matches*) and an optional reason.

* **By default every new link is only suggested** and waits in the review queue like any other suggestion. The
  import never records a decision nobody made.
* If you may review mappings, you can tick **"These links were already reviewed elsewhere"** when you confirm:
  they are then accepted with the method *imported* and **no reviewer is recorded**.
* A pair that is **already linked** (accepted, suggested or rejected) is left exactly as it is; the plan says
  "already linked".

## Frameworks (needs permission to manage frameworks)

On the framework pack card, download the **Excel template for a framework**: a Framework sheet (one row: key,
name, version, publisher, licence, profile, web address, description) and an Items sheet (code, title,
description, parent code). Upload the filled-in .xlsx where you would upload a pack file. It is turned into a
pack and checked like one: you see the same preview (counts, tree, warnings) and the same confirmation, and
problems are listed by sheet and row. Cross-references, crosswalks and tag lists in a framework need a JSON pack
file. Put only the framework's own wording in the file, and check its licence.

## Import history

At the bottom of the page: every applied import (curriculum, tags, mappings, framework), newest first, with when,
what, which version, who and how many rows were new or updated. You see your own; with permission to read the
audit log you see everyone's. It holds counts only, never the file, its name or what was in it.

## Limits

Files may be as large as the installation's upload limit (`PACK_MAX_UPLOAD_MB`) and have at most 5 000 rows a
sheet. The templates' headings and instructions are English for now.
