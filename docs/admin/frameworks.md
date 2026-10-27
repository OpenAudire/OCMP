# The framework library

The **Frameworks** page lists the frameworks that objectives can be mapped to, lets you browse
one as a tree, search it and see where its items are mapped. The design is in
[ADR 038](../adr/038-framework-library-and-browser.md). Frameworks are brought in with
[framework packs](framework-packs.md).

## Who sees what

- Anyone who can view the curriculum (`curriculum.view`) or manage frameworks
  (`frameworks.manage`) can open the page. Students, who only see published content in the
  explorer, do not get this entry.
- **Where mapped** shows only the curriculum your roles show, by the same rules as the
  curriculum screens. A module coordinator sees links from their own module and its sessions, a
  lecturer from their own sessions, the curriculum office from everything including drafts. A
  link you cannot see is left out of the list and of the counts, so a number never gives away
  hidden curriculum.
- **Delete** and **Import framework pack** appear only for people with `frameworks.manage`.

## The library

Each card is one framework (all its versions together) with its kind, status, size and number of
versions. Select a card to read its description, source, the **licence and usage** note, its
size and its versions. Always read the licence note before relying on a framework: it records
what the publisher allows.

Each version has **Browse** and, for managers, **Delete**. A version can be deleted only while
nothing depends on it: no objective may be mapped to it, no review may be assigned on it, and no
newer version may have been built on it (delete the newer one first). The version is hidden, not
erased, and the change history keeps a record. For a framework that is in use, change its status
(retired) instead of deleting it.

Frameworks that are copyrighted ship as blank templates, not as text. Download them from
**Import and export**, fill them from your institution's licensed copy and import them as a pack.

## Browsing one framework

- The tree on the left opens one level at a time, so a framework with thousands of items opens
  quickly. Select an item (or press Enter or Space) to see its description, where it sits and where
  it is mapped. The address keeps the selected item, so you can share a link to it.
- **Keyboard**: Up and Down move, Right opens an item or moves into it, Left closes it or moves to
  its parent, Home and End jump to the first and last row, Enter or Space selects. Only one row is
  in the Tab order.
- A long list of siblings shows the first 100. **Show more** and **Show earlier** rows load the
  rest.
- **Search** finds items by code or words (not case sensitive). Results show where each item sits;
  select one to see it, and **Show in tree** to open the tree at that item.

## Where an item is mapped

For the selected item the page lists the objectives linked to it that you can see. Each shows the
objective, where it is in the curriculum (a link to it), the review status in words (accepted,
suggested and not yet reviewed, or waiting for a second review), coverage out of 5, depth, and
warnings: **wording changed: check it still fits** and **reviewers disagree: discuss it**.
Rejected links are not listed. The list is read only; links are made in the mapping workspace.
