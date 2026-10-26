# ADR 034: Managing Tag Lists, Tagging Items and Inheritance

## Status

Accepted (Slice 1.8). Builds on ADR 015 (tag lists and tagging models), ADR 012
(permissions), ADR 027 (who sees what), ADR 028 (structure editing) and ADR 029 (copying).

## Context

The brief (sections 3 and 4) asks for configurable tag lists managed by the curriculum
office, and inheritance: "a tag or mapping set on a module objective can flow down to every
linked session. Always show a preview of every affected item before saving, and record the
inheritance source." ADR 015 stored the lists, values and taggings (with `inherited_from_id`)
and left the rules, the preview and the screens to this slice.

## Decision

### Managing lists and values
- Needs `taglists.manage` at the list's scope (Slice 1.10a, ADR 015): its faculty for a faculty
  list, the whole institution for an institution-wide list. Curriculum office at faculty level
  therefore manages its faculty's lists only; at institution level (and platform admin) every
  list. `POST /tag-lists` takes an optional `faculty_id` (omitted: institution-wide, which needs
  the instance permission), `GET /tag-lists/places` says where the user may create lists, and
  each list read carries `faculty_id`, `faculty_name` and `can_manage`. Endpoints: `GET/POST /tag-lists`, `PATCH/DELETE /tag-lists/{id}`,
  `POST /tag-lists/{id}/values`, `PATCH/DELETE /tag-values/{id}`. The screen is
  `/admin/tag-lists`.
- `GET /tag-lists` is open to every signed-in user, because people tag with the lists: they
  get the active lists they can see (institution-wide and their faculties') and active values
  only. Managers of a list also get its inactive tags, see it when inactive, and get how often
  each tag is used.
- A list's **key and kind cannot change** (imports use the key; a teaching-method list backs
  session formats). Name, description, applicable item types and the active flag can.
- A list or tag **in use cannot be deleted** (409): "in use" means a tagging, or a session
  that has it as its format. It is made *inactive* instead: existing tags stay, but it can no
  longer be applied. Deleting an unused list soft-deletes its tags with it.
- New tags go to the end of the list. Reordering tags is not part of this slice.
- Every change is audited through the ORM with the labels `taglist.create|update|delete` and
  `tagvalue.create|update|delete`.

### Tagging items
- Taggable in the builder: **modules, sessions (learning events) and objectives** (programme
  outcomes, module outcomes, session objectives). Programmes themselves are not versioned
  items, so a tag on one would not follow copy forward; the model allows it (ADR 015) but no
  screen or endpoint offers it.
- Needs `tagging.edit` at the scope that owns the item: the module, the session, or the
  programme for a programme outcome (module coordinators and above; lecturers do not have
  it). An item the user cannot see is a 404; only **draft** versions change (409).
- Endpoints: `POST /curriculum-items/{module|learning_event|objective}/{id}/tags`,
  `GET .../tag-preview?tag_value_id=` and `DELETE /taggings/{id}`. Reads (module, session,
  programme outcomes) carry each item's `tags` and the flags `can_edit_tags` and
  `can_edit_outcome_tags`.
- Only a list that applies to the item's kind, and only an active tag of an active list, can
  be applied (422).

### Inheritance rules
| Tagged item | Passes the tag to |
|---|---|
| Module | its sessions |
| Programme outcome | the module outcomes and session objectives linked beneath it, at any depth |
| Module outcome | the session objectives linked to it |
| Session, session objective | nothing |

- Inheritance is **chosen when tagging**, not automatic: the dialog first shows a preview of
  every item the tag would reach, each marked *will get the tag*, *already has this tag* or
  *this list is not used on this kind of item*, and a box "Also give this tag to the N items
  below" (ticked when there are any). Saving applies exactly what the preview listed as new.
- Every inherited tagging points to the **direct tagging it came from**, even when it came
  through several levels, so the source is always the item that was tagged. Removing the
  direct tag removes everything it passed on (deleted through the ORM, so each row is in the
  audit log).
- An item that already has the tag directly is left alone. One that has it inherited from
  another source gets a second tagging, so the tag stays when one source is removed.
- Tags are shown **once per item and tag**: a chip for the tag, its list, and in words where
  it came from ("Inherited from module HSC201 Cardiology", or "Set here and inherited from
  ..."). A tag whose source item was deleted is not shown.
- Only a **direct** tag can be removed (422 for an inherited one: remove it where it was set).
- Inheritance is applied at the moment of tagging ("apply once"). Items linked or added **later**
  do not receive the tag by themselves; copy forward and copying keep the tags and sources that
  exist (ADR 029, ADR 030).

### Passing a tag on to newer items (Slice 1.10a)
- "Apply once" stays. For a **direct** tag on a module or a programme or module outcome, the
  details panel counts the items below it that the tag has **not reached**: those that sit below
  it now, may carry the list, have no direct tag of it, and have no tagging that came from this
  tagging (`not_reached` on the item's tag). An item that has the tag only from *another* source
  counts as not reached, exactly as the Add tag preview marks it `new`.
- People who may tag see a notice with the count and a **Pass it on** button. It opens a dialog
  that previews the items exactly like the Add tag dialog (`GET /taggings/{id}/pass-on-preview`),
  then `POST /taggings/{id}/pass-on` gives the tag to the items marked `new`, each pointing to the
  direct tagging. Needs `tagging.edit` at the item's scope, draft versions only (409), an
  inherited tagging answers 422, audit label `tagging.pass_on`. Inherited rows are created through
  the ORM, so each reaches the audit log; removing the direct tag still removes all of them.

## Consequences

- No schema change and no migration: ADR 015 already holds everything.
- Migration 0016 adds `tag_lists.faculty_id` (ADR 015).
- Counting what a tag has not reached costs a few queries per directly tagged module or outcome
  when the item is read; sessions and session objectives pass nothing and are skipped.
- A later slice can show tags in search and filters, and add reordering of tags.
- No personal data is added: tags are institutional wording; the audit log already records
  the acting user's id.
