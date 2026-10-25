# ADR 029: Reordering and Copying Curriculum Items

## Status

Accepted (2026-10-25, Slice 1.4)

## Context

The brief asks for a tree editor "with drag-and-drop reorder, copy". Slice 1.3 (ADR 028)
added editing with scoped permissions and put new items at the end of their parent.
Drag and drop alone fails WCAG 2.2 success criterion 2.5.7 (dragging movements need a
single-pointer alternative) and cannot be used with a keyboard. Copying must decide what
a copy takes along: children, objectives, links, tags, mappings, role assignments.

## Decision

### Reordering
- `POST /phases/{id}/move`, `/modules/{id}/move` and `/learning-events/{id}/move` take
  `{"position": n}`: the item's new index (from 0) among its siblings. Siblings are the
  version's phases; the modules of the same phase (or the modules across phases, which
  include modules whose phase was deleted); the sessions of the same module. The service
  numbers the siblings 0, 1, 2... in the new order and writes only the rows whose
  position changed, through the ORM (so each change is in the audit log, labelled
  `curriculum.phase_move`, `curriculum.module_move`, `curriculum.learning_event_move`).
- A move index rather than a full ordered list: one small request per move, and a
  concurrent change elsewhere in the list does not make the request fail.
- Moving a module to another phase stays a change of its `phase_id` (Edit dialog).

### Copying
- `POST /phases/{id}/copy` (`name`, `module_codes`: a new code for every live module of
  the phase), `/modules/{id}/copy` (`code`, `name`, optional `phase_id`) and
  `/learning-events/{id}/copy` (`title`) answer 201 with the new item.
- The copy goes directly after the original; a module copied into another phase (or
  across phases) goes to the end there. Sessions are copied within their module only.
- A copy takes: its live children (phase: modules; module: sessions), the fields of each
  item except the LMS reference, the live objectives of each module and session (text,
  domain, taxonomy level, detected verb, quality flags, status, order), their upward
  links (to the copied parent when the parent was copied too, otherwise to the same
  parent), and the taggings of every copied item; an inherited tagging whose source was
  copied comes from the source's copy.
- Not copied: framework mappings (reviewed decisions about one objective; copying them
  would count coverage twice), role assignments (access decisions), the LMS reference (a
  copy is not the same LMS course), deleted rows, and links from objectives outside the
  copy. Copying a whole year forward with its role assignments is Slice 1.5.
- Module codes stay unique per version, ignoring case (409 for a taken or repeated code).
- Audit labels: `curriculum.phase_copy`, `curriculum.module_copy`,
  `curriculum.learning_event_copy`, with the source id.

### Permissions
Moving and copying follow ADR 028: phases and modules are the programme's structure
(`curriculum.edit` at the programme), sessions belong to their module (`curriculum.edit`
at the module). A lecturer with a session role cannot move or copy their session. The
UI shows the controls from the existing `can_edit` flags.

### Frontend
- **Keyboard and single-pointer path**: the selected item's details panel has **Move up**
  and **Move down** buttons (and **Copy**). After a move the confirmation is announced
  (`role="status"`); focus stays on the pressed button, or moves to the confirmation
  when that button has become unavailable (first or last place). The buttons are not
  disabled while a move runs, so focus is never lost.
- **Drag and drop** in the structure tree uses the browser's native drag and drop (mouse
  and, in current mobile browsers, touch): rows that can move show a grip icon, a line
  shows where the item will land, and only siblings accept a drop. No library was added:
  the tree is a custom ARIA tree (ADR 027), and the libraries' keyboard sensors would
  compete with its arrow keys; the keyboard path is the buttons above. The tree says
  under its title how to change the order.
- Items without siblings show no move controls.
- The copy dialog states what is and is not copied, suggests "<name> (copy)", asks for
  the new module code(s), and selects the copy afterwards.

## Consequences

- Drag and drop has no live preview of the reordered list; the tree updates after the
  save. A library can replace the native events later without API changes.
- Positions are only meaningful within a group of siblings; reports must order modules
  per phase, as the structure response already does.
- Slice 1.5 (copy academic year forward) can reuse the copy service's remapping of
  objectives, links and taggings for a whole version.
