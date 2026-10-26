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
- Needs `taglists.manage` for the whole institution (curriculum office at institution level,
  platform admin). Endpoints: `GET/POST /tag-lists`, `PATCH/DELETE /tag-lists/{id}`,
  `POST /tag-lists/{id}/values`, `PATCH/DELETE /tag-values/{id}`. The screen is
  `/admin/tag-lists`.
- `GET /tag-lists` is open to every signed-in user, because people tag with the lists: they
  get active lists and active values only. Managers also get inactive ones and how often each
  tag is used.
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
- Inheritance is applied at the moment of tagging. Items linked or added **later** do not
  receive the tag by themselves; copy forward and copying keep the tags and sources that
  exist (ADR 029, ADR 030).

## Consequences

- No schema change and no migration: ADR 015 already holds everything.
- New tag lists for a faculty rather than the institution would need a scope column on
  `tag_lists`; today they are institution-wide.
- A later slice can re-apply a tag to newly linked items (a "re-apply" action on the source),
  show tags in search and filters, and add reordering of tags.
- No personal data is added: tags are institutional wording; the audit log already records
  the acting user's id.
