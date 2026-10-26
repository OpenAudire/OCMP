# Tag lists and tagging

Tag lists hold the labels people attach to the curriculum: teaching methods, assessment
methods, themes, longitudinal threads, keywords, resources, EPAs and any custom list. The
curriculum office keeps the lists; module coordinators, programme directors and the
curriculum office tag modules, sessions and objectives with them. The design is in
[ADR 015](../adr/015-tag-lists-and-tagging.md) and [ADR 034](../adr/034-tag-lists-and-tagging-ui.md).

## Keeping the lists

Open **Admin**, then **Tag lists** (`/admin/tag-lists`). You need the `taglists.manage`
permission. The curriculum office and platform admin roles have it; custom roles need it added
by hand. Where you hold it decides which lists you keep:

| You hold `taglists.manage` for | You can keep |
|---|---|
| The whole institution (curriculum office or platform admin assigned to the institution) | Every list: institution-wide ones and every faculty's |
| One faculty (curriculum office assigned to that faculty) | That faculty's lists only. You can also create lists for it, but not institution-wide lists, and you cannot change another faculty's lists or the institution-wide ones |

Each list shows who keeps it: **Whole institution** or a faculty name. Lists you cannot change
are shown without edit buttons. When you create a list, **Kept for** says where it belongs; it
cannot be changed afterwards (neither can the key or kind).

**Who sees and uses a list.** Institution-wide lists can be used by everyone who tags. A
faculty's list is visible to people who hold a role in that faculty (or in one of its
programmes, modules or sessions) and to people with an institution-wide role, and it can be
used only on items of that faculty, including as a session's format or an assessment's method.
Packs import tag lists as institution-wide lists, so importing a pack with tag lists needs the
permission for the whole institution.

- **New tag list**: a name, a short **key** (lower-case letters, digits, hyphens and
  underscores; imports use it), a **kind** and which items it may tag (modules, sessions,
  objectives). The key and the kind cannot be changed afterwards. Teaching-method lists are
  the ones that can be chosen as a session's format.
- **Edit list**: name, description and the items it applies to. Narrowing the items leaves
  existing tags where they are; it only stops new ones.
- **Add tag**: a label (unique in the list) and an optional code, a stable identifier for
  later imports (also unique in the list).
- **Make inactive**: the list or tag stays on everything it is already on, but nobody can
  apply it again. Make it active to allow that again.
- **Delete**: only a list or tag that nothing uses. A tag is in use when an item carries it
  or a session has it as its format. Deleting a list deletes its tags. Otherwise make it
  inactive.

Every change is recorded in the change history (`taglist.create`, `taglist.update`,
`taglist.delete`, `tagvalue.create`, `tagvalue.update`, `tagvalue.delete`).

## Who can tag

Tags are added and removed in the curriculum builder, in the details of the selected item.
People with `tagging.edit` at the right scope see an **Add tag** button:

| Item | Needs `tagging.edit` at |
|---|---|
| A programme outcome | The programme (or its faculty, or the institution): curriculum office, programme directors |
| A module and its outcomes | The module (or above): also module coordinators |
| A session and its objectives | The session (or above) |

Lecturers do not have `tagging.edit` in the built-in roles. Only **draft** versions can be
tagged; tags in published versions are read-only. Everyone who can see an item sees its tags.

## Inheritance

A tag can flow down from the item you tag:

| You tag | The tag can also go to |
|---|---|
| A module | Its sessions |
| A programme outcome | The module outcomes and session objectives linked beneath it |
| A module outcome | The session objectives linked to it |

When you pick a tag for such an item, the dialog **lists every item the tag would reach**
before anything is saved. Each is marked *will get the tag*, *already has this tag* or *this
list is not used on this kind of item*. The box "Also give this tag to the N items below" is
ticked when there are any; clear it to tag only this item.

In the details panel each tag shows its list, and where it came from:

- a tag you set shows a **Remove** button;
- an inherited tag says **Inherited from** the module, session or objective it was set on,
  and has no Remove button. Remove it at its source: that also removes everything it passed
  on;
- a tag set here that is also inherited says **Set here and inherited from** ...

Inheritance is applied when you tag. A session or objective added or linked afterwards does
not receive the tag by itself; copying an item or copying a year forward keeps the tags and
their sources.

**Passing a tag on later.** When a tag you set on a module or an outcome has not reached items
that were added or linked below it afterwards, the details panel says so ("PBL has not reached 2
newer items below") and offers **Pass it on**. The dialog lists those items first, exactly as
when you add a tag; confirming gives them the tag, with this item as the source. Items that
already have the tag set directly are left alone. Only people who may tag see the notice, and
only in draft versions.

## Through the API

`GET /api/v1/tag-lists` returns the lists (everyone signed in gets the active ones they can
see; managers of a list also get its inactive tags and each tag's usage, and `can_manage` says
which lists you may change). `GET /tag-lists/places` says where you may create lists. The
management endpoints are `POST
/tag-lists` (with `faculty_id` for a faculty's list), `PATCH`/`DELETE /tag-lists/{id}`, `POST /tag-lists/{id}/values` and
`PATCH`/`DELETE /tag-values/{id}`. Tagging uses `GET
/curriculum-items/{module|learning_event|objective}/{id}/tag-preview?tag_value_id=`, `POST
/curriculum-items/{...}/{id}/tags` (`{"tag_value_id": "...", "inherit": true}`) and `DELETE
/taggings/{id}`; `GET /taggings/{id}/pass-on-preview` and `POST /taggings/{id}/pass-on` pass a
direct tag on to newer items. See the interactive API docs for the details.
