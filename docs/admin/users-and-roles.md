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
