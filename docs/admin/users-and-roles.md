# Users and roles

People get access to Curriculum in Context through **roles**. A role is a set of permissions given to a
person at a **scope**: the whole institution, a faculty, a programme, a module or a
learning event. A role applies at its scope and everything below it, never above or
beside it. The API enforces every permission; the web application only hides what a
person cannot use.

## Built-in roles

| Role | Key | Can be given at | Purpose |
|---|---|---|---|
| Platform admin | `platform_admin` | institution | Install settings, SSO, AI provider, integrations, users and roles. |
| Curriculum office | `curriculum_office` | institution, faculty | Frameworks, tag lists, curriculum versions and all reports. |
| Programme director | `programme_director` | programme | Programme outcomes and structure, coverage review, publishing versions. |
| Module coordinator | `module_coordinator` | module | Modules, learning events, objectives, mapping and AI suggestion review. |
| Lecturer / facilitator | `lecturer` | module, learning event | Edit the objectives of their own sessions and view their schedule. |
| Mapper / reviewer | `mapper` | programme, module | Create and review mappings (first and second review). |
| Student | `student` | institution, programme | Read-only explorer and search over published content. |
| External reviewer | `external_reviewer` | programme | Time-limited read-only access to evidence packs. Needs an expiry date. |

The built-in roles cannot be changed; they are updated with each Curriculum in Context version. Platform
admins can add custom roles. A person can give a role only if they have the permission
to assign roles at that scope **and** every permission of the role there, so nobody can
give more access than they have. The last active platform admin cannot be removed or
deactivated.

## Who sees which curriculum

The **Curriculum** section (the curriculum builder) and the curriculum API show each
person only what their roles allow:

- A role at the institution, a faculty or a programme shows whole curriculum versions:
  every phase, module and session, and the programme outcomes.
- A role at a module shows that module with its sessions. A role at a session shows that
  session, under its module's name.
- Roles with `curriculum.view` (staff roles) show draft, published and archived
  versions. Roles with only `curriculum.view_published` (students, external reviewers)
  show published versions only.

People with a module or session role see a note that they see only the parts they work
on. Anything a person cannot see is answered as "not found", so nobody learns which
other programmes or modules exist.

## Who can change the curriculum structure

In the curriculum builder, people with `curriculum.edit` (curriculum office, programme
directors, module coordinators) see **Add**, **Edit** and **Delete** buttons next to the
selected item, as far as their role reaches:

| Change | Needs `curriculum.edit` at |
|---|---|
| Add, rename, reorder, copy or delete a phase; add, reorder, copy or delete a module; move a module to another phase | The programme (or its faculty, or the institution) |
| Change a module's code, name, credits, NQF level, description or LMS reference; add, reorder, copy or delete its sessions | The module (or above) |
| Change a session | The session (or above) |

So a module coordinator can maintain their own module and put its sessions in order, but
cannot add, copy or reorder modules, delete their module or move it to another phase. Lecturers and mappers cannot
change the structure. The API checks every change; the buttons only follow the roles.

- **Deleting** is a soft delete: the item disappears from the builder but its rows and
  history stay in the database. Deleting a module also deletes its sessions and all their
  objectives; deleting a session deletes its objectives. A phase can only be deleted once
  it holds no modules. There is no restore screen yet.
- **Reordering**: drag a phase, module or session in the structure tree to another place
  among its neighbours, or select it and use **Move up** and **Move down** (which work
  with the keyboard). A module moves to another phase through **Edit**.
- **Copying** places the copy right after the original (a module can also be copied into
  another phase). A copied module takes its sessions; a copied phase takes its modules,
  each under a new code that you enter; objectives, their upward links and tags come
  along. Links to framework items, role assignments and the LMS reference are not copied:
  the copy starts unmapped, and coordinators of the original are not coordinators of the
  copy until someone assigns them.
- Every change is recorded in the audit log with who made it (`curriculum.phase_create`,
  `curriculum.module_update`, `curriculum.learning_event_delete`,
  `curriculum.module_move`, `curriculum.phase_copy` and so on).
- Only **draft** versions can be changed; published and archived versions are read-only
  (409). See "Publishing and copying a year forward" below.
- Roles held at a deleted module or session stay listed but give no access to anything.

## Who can edit objectives

Programme outcomes, module outcomes and session objectives are edited in the curriculum
builder, in the selected item's details. People with `objectives.edit` see **Add**,
**Edit** and **Delete** buttons next to the objectives they may change:

| Change | Needs `objectives.edit` at |
|---|---|
| Programme outcomes | The programme (or its faculty, or the institution): curriculum office, programme directors |
| A module's outcomes | The module (or above): also module coordinators |
| A session's objectives | The session (or above): also lecturers of that session |

Each objective has its wording, a **domain** (knowledge, skill, attitude), a **taxonomy
level** (from any scale, such as Bloom or Miller), a status (draft, ready for review,
approved, retired) and **upward links** to the broader outcomes it contributes to: a module outcome to programme
outcomes, a session objective to its module's outcomes or to programme outcomes.

- Anyone who sees part of a version can read, for choosing links only, the programme
  outcomes and (for a session objective) the outcomes of the session's own module. So a
  lecturer who holds only a role on one session can still link their objectives upward.
  Nothing else above their session opens up (ADR 032).
- **Status**: anyone who may edit an objective sets *draft* or *ready for review*. Setting
  *approved* or *retired* (and leaving them) needs `objectives.approve` at the same scope:
  module coordinators, programme directors, the curriculum office and platform admins have
  it, lecturers do not. If a lecturer changes the wording of an approved objective, it goes
  back to *ready for review*. Custom roles need `objectives.approve` added by hand.
- **Mappings**: when the wording of an objective changes, its accepted framework mappings
  stay accepted but are marked **needs re-check** (a chip in the builder, and a flag
  reports will show) until someone with `mapping.review` confirms them.
- Only **draft** versions can be changed. Deleting an objective is a soft delete; it
  disappears from the builder and reports, and the deletion is recorded in the change
  history.
- Audit labels: `curriculum.objective_create`, `curriculum.objective_update`,
  `curriculum.objective_delete`.

## Objective quality checker

While someone writes an objective, a **Quality check** box under the wording flags likely
problems and suggests a taxonomy level from the verb. It uses fixed rules only: nothing is
sent to an AI service and nothing is saved by a check. The findings are advice and never
stop anyone saving.

- **Warnings**: vague verbs (understand, know, appreciate, "be aware of"), more than one
  verb, very long wording (over 40 words), no domain, no upward link.
- **Notes**: no verb the checker knows, very short wording, a "Students will be able to"
  lead-in, hard-to-measure words (appropriate, various), and a chosen level that differs from
  the verb's usual level.
- **Suggested level**: the verb is looked up in the verb lists of the taxonomy levels (they
  come with the scale, from its pack). A button such as "Use Understand (Bloom)" sets the
  level when clicked; nothing is set on its own.
- **Check wording** (version bar) lists the findings for every objective the person may see
  in the open version, with filters for severity and rule and a link to each objective. It is
  for people who hold `objectives.edit` somewhere; it shows only what they may read.
- Who can use it: the live check needs `objectives.edit` at the objective's owner (as for
  adding it); the list needs `objectives.edit` anywhere. It is limited to 240 checks a minute
  per person.
- The wording lists are versioned files per language (`app/services/objective_rules/en.json`);
  only English exists so far. See ADR 033.

## Publishing and copying a year forward

Each programme has one version per academic year. A version is a **draft** (editable, seen
only by staff), **published** (read-only, seen by students and everyone who may view
published versions) or **archived** (read-only, hidden from students).

| Action | Needs | Notes |
|---|---|---|
| Publish a draft | `curriculum.publish` at the programme | The draft needs at least one module. |
| Return a published version to draft | `curriculum.publish` and `curriculum.unpublish` (programme directors and above) | To correct it; students stop seeing it until it is published again. A written reason is required (up to 500 characters) and is recorded in the change history as `curriculum.version_unpublish`. Do not put personal data in it. |
| Archive a published version, or publish an archived one again | `curriculum.publish` | |
| Copy a version forward | `curriculum.edit` at the programme | Makes a new draft for a free academic year. |
| Copy role assignments along | also `roles.assign` and every permission of each role | |
| Delete a draft | `curriculum.edit` at the programme | Soft delete of the version and its contents; the year becomes free. |
| Compare two versions | seeing both whole | Added, removed and changed items. |

- **Copy forward** copies every phase, module, session and objective (programme outcomes
  too), their upward links, tags and framework links with their review state. LMS
  references are not copied. Each copied item remembers its original, so the comparison
  follows items across years even when they are renamed.
- **Role assignments** at modules and sessions are listed in the copy dialog with every
  person's name; each is ticked by default and can be unticked. Assignments that have ended,
  or whose account is deactivated or deleted, or whose role you may not grant, are shown as
  not copied. People who cannot assign roles copy the structure without roles.
- **Compare versions** lists phases, modules, sessions and objectives that were added,
  removed or changed, with the old and new value of each changed field. Items are matched
  by their copy history first, then by phase name, module code, session title and
  objective text. Order, upward links, tags and framework links are not compared.
- Audit labels: `curriculum.version_publish`, `_unpublish`, `_archive`, `_unarchive`,
  `_copy_forward` and `_delete`.
- The demo programme has a published version for the current year and a draft for the
  next year, made by copy forward with a few changes so the comparison has something to
  show. Running `load-demo` again on an install loaded earlier adds the draft.

## Managing users before the admin screens exist

User and role screens arrive in Phase 1. Until then, platform admins manage access
through the API. The commands below run in a Linux shell with `curl` and `jq`
(`sudo apt install jq`), on the server or any computer that can reach the site.

### Sign in

```bash
SITE=https://curriculum.example.ac.za
JAR=$(mktemp)                      # holds the session cookie
read -r -p "Email: " EMAIL
read -r -s -p "Password: " PASSWORD; echo
CSRF=$(jq -n --arg email "$EMAIL" --arg password "$PASSWORD" '$ARGS.named' \
  | curl -sS --fail-with-body -c "$JAR" -H 'Content-Type: application/json' \
      -d @- "$SITE/api/v1/auth/login" \
  | jq -r .csrf_token)
unset PASSWORD

# Calls the API with the session; state-changing requests need the CSRF token.
api() { curl -sS --fail-with-body -b "$JAR" -H "X-CSRF-Token: $CSRF" \
          -H 'Content-Type: application/json' "$@"; echo; }
```

### Create a user

Create the account with a random password nobody knows, then ask the person to choose
their own with **Forgotten password** on the sign-in page (this needs
[email](../operations/configuration.md#email)). With [single sign-on](sso.md) and
automatic account creation, skip this step: the account appears at the first sign-in.

```bash
api -d "$(jq -n --arg password "$(openssl rand -base64 24)" \
  '{email: "a.lecturer@example.ac.za", display_name: "A. Lecturer", password: $password}')" \
  "$SITE/api/v1/users"
```

The answer includes the new user's `id`.

### Find a user

```bash
api "$SITE/api/v1/users?search=lecturer" | jq '.items[] | {id, display_name, is_active}'
```

### Give a role

At the institution scope (no `scope_id`):

```bash
api -d '{"user_id": "<user id>", "role_key": "curriculum_office", "scope_type": "instance"}' \
  "$SITE/api/v1/role-assignments"
```

For a faculty, programme, module or learning event, set `scope_type` to `faculty`,
`programme`, `module` or `learning_event` and add `"scope_id": "<its id>"`. Add
`"expires_at": "2027-06-30T00:00:00Z"` for access that should end on a date.

### See and remove roles

```bash
api "$SITE/api/v1/users/<user id>/role-assignments" | jq '.[] | {id, role: .role.key, scope_type, scope_id}'
api -X DELETE "$SITE/api/v1/role-assignments/<assignment id>"
```

### Deactivate or reactivate a user

Deactivation ends the person's sessions at once and stops them signing in; their history
is kept.

```bash
api -X PATCH -d '{"is_active": false}' "$SITE/api/v1/users/<user id>"
api -X PATCH -d '{"is_active": true}' "$SITE/api/v1/users/<user id>"
```

### Sign out

```bash
api -X POST "$SITE/api/v1/auth/logout"; rm -f "$JAR"
```

The full API, with every field, is listed at `https://<your site>/api/docs`.

## Recover admin access

If no platform admin can sign in (for example the only admin left the institution), an
operator with access to the server can create a new one, or promote an existing account:

```bash
cd /opt/ocmp/deploy
docker compose exec api python -m app.cli create-admin --email it.admin@example.ac.za --name "IT Admin"
```

The command asks for the password of a new account. It is recorded in the audit log.
