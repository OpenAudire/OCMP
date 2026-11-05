# Admin basics

This page is for platform admins and server operators after [installation](../operations/install.md).
Commands marked "on the server" run in `/opt/ocmp/deploy`; API examples use the `api`
helper from [Users and roles](users-and-roles.md#sign-in).

## First steps after setup

1. Sign in as the administrator created by the setup wizard and open **Account** to check
   your details.
2. Give a second person the platform admin role, so access does not depend on one
   account ([Users and roles](users-and-roles.md)).
3. Choose the institution's terminology and profiles (below).
4. Optionally set up [single sign-on](sso.md).
5. Confirm that [backups](../operations/backup-restore.md) run and that a restore test
   works.

## Terminology and profiles

**Terminology.** Curriculum in Context's curriculum words can be renamed to match the institution, for
example "Course" instead of "Module". The words that can be renamed are `programme`,
`curriculum_version`, `phase`, `module`, `learning_event`, `objective`, `framework` and
`framework_item`. Each needs a singular and a plural.

**Profiles.** `core` is always on. `health` (health sciences) adds the role balance
report, the council evidence pack layout and clinical placements as they become
available.

**Mapping review policy.** `four_eyes` requires a second, different reviewer before an
accepted mapping counts; `second_review_for_rejects` does the same for rejections. Both
are off by default. `bulk_accept_min_percent` (default 80, from 50 to 100) is the lowest confidence
"Accept all" may use and `bulk_accept_max_links` (default 200, from 1 to 1000) is how many links one
"Accept all" handles (see [Review queue](review-queue.md)). Two settings are for
[AI suggestions](mapping.md#suggesting-links-with-ai): `ai_min_coverage` (default 1, from 1 to 5) drops
suggestions that cover less than that, and `ai_prefer_specific_item` (default on) stops the AI from
suggesting a parent item next to one of its children.

**Credits and notional hours.** The `credits` section sets the figures behind the credit check
(see [Assessments and credits](assessments-and-credits.md)): `hours_per_credit` (default 10),
`tolerance_percent` (10), `credits_per_year` (120) and `min_exit_level_credits` (off; a whole
number to check the credits at the programme's NQF exit level).

**Coverage reports.** The `coverage` section sets the numbers behind the
[coverage and gap reports](coverage-reports.md): `multiple_match_n` (default 3, from 1 to 20: the links
that make an item covered by multiple match), `subordinate_min_percent` (50: the gap report lists the
groups where fewer of the items below are covered) and `weighted_low_percent` (40: the gap report lists
the items under this share of full coverage). Two more numbers belong to the report
[Taught in many sessions](curriculum-reports.md): `repeat_min_sessions` (default 4, from 2 to 100) and
`repeat_spread` (1.5, from 0 to 5 standard deviations). Every report prints these numbers.

Settings screens arrive in Phase 1. Until then, change them through the API (needs the
platform admin role). Each section sent replaces the stored one; sections left out stay
as they are:

```bash
api -X PATCH "$SITE/api/v1/institution/settings" -d '{
  "terminology": {"module": {"singular": "Course", "plural": "Courses"}},
  "profiles": ["core", "health"],
  "mapping": {"four_eyes": false, "second_review_for_rejects": false,
              "bulk_accept_min_percent": 80, "bulk_accept_max_links": 200,
              "ai_min_coverage": 1, "ai_prefer_specific_item": true},
  "credits": {"hours_per_credit": 10, "tolerance_percent": 10, "credits_per_year": 120}
}'
api "$SITE/api/v1/institution"     # the current settings
```

Send `null` for a section to return it to the default. Changes are recorded in the audit
log and appear for users after they reload the page.

## Audit log

Every change to curriculum, framework, mapping, organisation and access data is recorded
with who made it, when, and the values before and after. Admin views of personal data
(user records) are recorded too. Entries cannot be changed or deleted, except by the
retention purge below and by anonymisation when a person is deleted.

```bash
# The 20 newest entries
api "$SITE/api/v1/audit-log?limit=20" | jq '.items[] | {occurred_at, action, entity_type, actor_id}'
# What one person did since a date
api "$SITE/api/v1/audit-log?actor_id=<user id>&since=2026-10-01T00:00:00Z"
```

Other filters: `entity_type` (table name, such as `modules` or `role_assignments`),
`entity_id`, `action` (`create`, `update`, `soft_delete`, `restore`, `delete`, `view`), `until`, `offset`.

## Retention

Two kinds of records are kept only as long as the institution decides (POPIA):

| Records | Setting in `.env` | Command (on the server) |
|---|---|---|
| Audit log entries | `AUDIT_LOG_RETENTION_DAYS` (default `0`: keep forever) | `docker compose exec -T api python -m app.cli purge-audit-log` |
| Stored AI prompts and responses | `AI_CALL_RETENTION_DAYS` (default `365`) | `docker compose exec -T api python -m app.cli purge-ai-content` |

The commands delete what is older than the setting. Run them on a schedule, for example
weekly with cron:

```cron
15 3 * * 0 cd /opt/ocmp/deploy && docker compose exec -T api python -m app.cli purge-audit-log 2>&1 | logger -t ocmp-purge
20 3 * * 0 cd /opt/ocmp/deploy && docker compose exec -T api python -m app.cli purge-ai-content 2>&1 | logger -t ocmp-purge
```

## Monitoring

| Address | Answer when all is well |
|---|---|
| `https://<your site>/health` | `{"status":"healthy"}`: the API is running |
| `https://<your site>/ready` | `{"status":"ready","database":"up","redis":"up"}`; HTTP 503 when the database or Redis is down |

Point the institution's monitoring at `/ready`. On the server, `docker compose ps -a`
shows the state of every service, and `docker compose logs --tail 100 <service>` the
recent log. Logs are JSON lines; they contain user ids but never passwords, tokens or
email addresses.

## Command reference

All on the server, as `docker compose exec api python -m app.cli <command>`:

| Command | What it does |
|---|---|
| `setup-token` | Shows the setup token while the first-run setup is pending. |
| `create-admin --email <address> --name "<name>"` | Creates a platform admin, or promotes an existing account ([recover admin access](users-and-roles.md#recover-admin-access)). |
| `sync-roles` | Creates or updates the built-in roles (runs automatically on every start). |
| `load-demo` | Loads the fictional demo programme (once; see [Install](../operations/install.md#try-curriculum-in-context-with-the-demo-data)). With `OCMP_DEMO_OFFICE_PASSWORD` set it also makes the faculty-scoped demo account `curriculum.office@example.org`; run again with it set to add the account to an earlier load. |
| `snapshot-metrics` | Records today's key figures of every draft and published version for the [committee dashboard](committee-dashboard.md) trend lines (counts only). The Compose `scheduler` service runs it at start and every 24 hours; run it from your own scheduler otherwise. Safe to repeat: the same day is replaced. |
| `remove-demo [--apply]` | Removes the fictional demo data: the demo programme with all its versions and what is in them, the demo faculty (if no other programme is in it), the demo framework (if nothing else is mapped to it), the demo tag lists (if nothing else uses them; otherwise they are kept and the command says so), the demo curriculum-office account and the demo gold set. **A dry run unless `--apply`**: it lists exactly what would go. Things are found by the demo's own codes, so nothing else is touched; the institution and taxonomy scales stay. Audited as `demo.remove`. |
| `clean-orphan-links [--apply]` | Data hygiene for installs from before 1.14b: lists (dry run, the default) or, with `--apply`, soft-deletes mapping links whose objective was already deleted. Audited as `mapping.orphan_cleanup`; safe to repeat. See [Mapping](mapping.md#deleting-objectives-and-their-links). |
| `embed-all` | Makes the embeddings of every objective and framework item that lacks a current one, and removes vectors of deleted items; also finds near-duplicate objectives. Needs `EMBEDDINGS_LOCAL=true` and the `embeddings` service ([Embeddings](../operations/embeddings.md)). Safe to repeat. |
| `embeddings-status` | Says whether the embeddings server answers (`off`, `ready` or `unreachable`) and how many objectives and framework items have a vector. Exits with 1 when unreachable. |
| `eval-template [--framework <name>] [--out <file>]` | Writes the empty Excel gold-set template ([Checking the AI's mapping](ai-evaluation.md)). |
| `eval-import <file> --name <name> --framework <name> [--dry-run]`, `eval-import --demo` | Checks and imports a filled-in gold set (every problem listed with its row; nothing saved unless the file is sound), or the fictional demo set. |
| `eval-run --gold-set <name> --version <id> --email <address>` | Asks the AI to map a gold set's objectives (nothing is saved) and prints precision, recall, F1 and kappa at each minimum coverage and what bulk accept would do at each floor. Costs money. |
| `eval-report [--gold-set <name>] [--run <id>] [--min-coverage N]` | Compares evaluation runs by prompt version and model, or prints the figures of one run. |
| `purge-audit-log [--days N]` | Deletes audit log entries older than N days (default from `.env`). |
| `purge-ai-content [--days N]` | Clears stored AI prompts and responses older than N days. |
| `new-encryption-key` | Prints a new key for `SECRETS_ENCRYPTION_KEYS` ([AI settings](ai.md#encryption-keys-and-rotation)). |
| `rotate-secrets` | Re-encrypts stored secrets (AI provider keys) with the newest encryption key; lists any it cannot read. |
