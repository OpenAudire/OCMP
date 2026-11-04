# Personal data inventory

This inventory lists every place Curriculum in Context stores or processes personal information, why, and
for how long, to support the institution's obligations under the Protection of Personal
Information Act (POPIA). It describes Curriculum in Context as built at the end of Phase 0 and must be
updated whenever a change adds or changes personal data (see `CLAUDE.md`).

The institution running Curriculum in Context is the **responsible party**. If someone else hosts it for
the institution, that party is an **operator** and needs a written agreement (POPIA
sections 20 and 21). Curriculum in Context is self-hosted: no personal information leaves the server
except as listed under [Sent outside Curriculum in Context](#sent-outside-curriculum-in-context).

!!! note "Not legal advice"
    This document describes what the software does. The institution's information officer
    decides lawful basis, retention periods and notices.

## Whose information

- **Staff users**: administrators, curriculum office, programme directors, module
  coordinators, lecturers, mappers and reviewers, external reviewers.
- **Students**, when given the student role.

Curriculum in Context holds **no student records** (marks, registrations, health data) and is not designed
to: curriculum content (objectives, sessions, frameworks) is not personal information.
Free-text fields such as descriptions must not be used for personal information about
students or patients.

## Database (PostgreSQL)

| Data | Where | Purpose | Source | Retention |
|---|---|---|---|---|
| Email address | `users.email` | Sign-in, password reset, notices | Admin, setup wizard or identity provider | While the account exists. Deleting an account (`DELETE /api/v1/users/{id}`) replaces it with a placeholder, replaces the display name, clears the password hash and removes roles and sign-in identities; the row stays for authorship |
| Demo account | `users` (`curriculum.office@example.org`, fictional address) | Trying faculty-scoped tag lists on a trial install | `load-demo` with `OCMP_DEMO_OFFICE_PASSWORD` set; not made otherwise | Until deleted by an admin; the password is never in the data files, only its Argon2id hash in the database |
| Display name | `users.display_name` | Shown to colleagues, attribution of work | As above | While the account exists |
| Password hash (Argon2id) | `users.password_hash` | Local sign-in; the password itself is never stored | User | Until changed or the account is removed; empty for SSO-only accounts |
| Active flag, last sign-in time | `users.is_active`, `users.last_login_at` | Access control, finding unused accounts | System | While the account exists |
| SSO identity: provider and subject id | `user_identities.issuer`, `.subject`, `.last_login_at` | Matching single sign-on to the account (never by email) | Identity provider | Deleted with the account |
| Roles held, their scope and expiry | `role_assignments` | Authorisation. Copying a year forward can copy module and session assignments to the new year's items; the copy dialog shows holders' display names to people who may assign roles | Admins | Until removed; time-limited roles expire |
| Authorship of records | `created_by_id` on every table | Accountability for curriculum changes | System | Kept; set to empty when the user is deleted |
| Review decisions | `mapping_links.first_reviewer_id`, `.second_reviewer_id`, review times | Four-eyes review of mappings | System | Kept with the mapping; set to empty when the user is deleted |
| Review assignments | `review_assignments.reviewer_id` | Allocating review work | Admins | Deleted with the user |
| Audit log | `audit_log.actor_id`, entries about users | Accountability, POPIA access log of admin views of user records | System | `AUDIT_LOG_RETENTION_DAYS` (default: kept). Email, name and password hash are never written to the log, only that they changed. When a user is deleted, `actor_id` is cleared. Operation labels can carry a short free-text reason typed by staff (returning a published version to draft, reopening a mapping); the screens say not to enter personal data |

## AI processing

AI is off by default. When an administrator chooses a provider (Admin > AI settings, ADR 042), the
only thing sent is curriculum text built from fixed templates and allow-listed fields (objective
text, framework items, module and session titles and descriptions, study-guide text). Personal
information must never be sent to an AI provider, and a privacy guard enforces this in code before any
provider is called (`app/ai/privacy.py`): email addresses, phone numbers, ID, student and staff
numbers, IP addresses, labelled hospital, folder and file numbers, labelled dates of birth, titles
(English, Afrikaans, isiZulu) followed by a name and the names of this installation's users are found
and the call is refused (or, if the administrator chose it, the found text is replaced by a
placeholder and checked again). A refusal is recorded with counts and kinds only, never the text.

| Data | Where | Purpose | Retention |
|---|---|---|---|
| The prompt as sent (after the guard) and the provider's answer | `ai_run_calls.request`, `.response`, `.error_message` | Audit of every AI call | Cleared after `AI_CALL_RETENTION_DAYS` (default 365) by `purge-ai-content`; the run, token counts and timings are always kept. Curriculum text only; it can hold personal information only if staff typed it into a curriculum field and the guard did not recognise it |
| Who made a call or run, and when | `ai_runs.created_by_id`, `ai_run_calls.created_by_id`, timestamps | Accountability, budgets | Kept; set to empty when the user is deleted |
| Who acknowledged the warning about text leaving South Africa, and when | `ai_settings.ack_by_id`, `.ack_at` | POPIA transparency about the transfer | Kept; set to empty when the user is deleted |
| AI provider API key | `ai_provider_configs.api_key_encrypted` (encrypted, ADR 041) | Calling the provider | Until removed or replaced. Not personal data; a secret. It is never returned by the API, never in the audit log (the column is recorded as "changed" only) and never in a log. Backups hold only the ciphertext |
| That an uploader confirmed a study guide holds no real patient information: the user (audit actor), the time, the version of the confirmation text, a SHA-256 of the file content and its size. **Not the file name** (it could carry a person's name) and not the content | `audit_log` entries `study_guide_confirmation` (Slice 1.14a; written by the study-guide upload, Slice 1.18) | Accountability for what may be sent to an AI provider | As the audit log (`AUDIT_LOG_RETENTION_DAYS`); the actor column is emptied when the user is deleted |
| Which objective was mapped to which framework item by which run, the AI's rationale (one sentence) and the words of the objective it quoted | `mapping_links` (source `ai`, `ai_run_id`, `rationale`, `evidence_quote`, `confidence`), `ai_runs.scope`, progress counters (`total_items`, `done_items`, `failed_items`, `links_created`) | Showing AI suggestions for review (Slice 1.16) | Kept with the mapping (deleted with its objective, ADR 043). Curriculum text only. The person who started the run is `ai_runs.created_by_id` and the audit actor of the suggestions; set to empty when the user is deleted |
| Earlier reviewer decisions on similar objectives (the objective's words, the item, accepted or rejected) | Inside the prompt of a mapping call, stored in `ai_run_calls.request` | Giving the model examples of what the institution counts | As the prompt (cleared after `AI_CALL_RETENTION_DAYS`). Never the reviewer's name: only the decision |
| The wording of an objective being written, the checker's fixed sentences, the taxonomy levels with their verbs, and the AI's suggested rewrite or classification with its reason | `ai_run_calls.request` and `response` (runs of type `rewrite` and `classification`; the person is `ai_runs.created_by_id`) | Showing a measurable rewrite or a suggested domain and level (Slice 1.17). Nothing is saved on the objective until a person saves it | As the prompt (cleared after `AI_CALL_RETENTION_DAYS`). Curriculum text only; the guard refuses wording that looks like personal information |
| The text of an uploaded study guide (in pieces), the module's title and what the AI proposed from it | `ai_run_calls.request` and `response` (runs of type `extraction`) and, for one hour, Redis `study-guide:<run id>` | Reading learning outcomes out of a study guide (Slice 1.18). The file is read in the request and **never stored; its name is never read or recorded** | The Redis copy: 1 hour, deleted when the run ends. The call record: as the prompt (cleared after `AI_CALL_RETENTION_DAYS`) |
| Import jobs: kind (curriculum, tags, mappings, framework), curriculum version, status and row counts of an applied import (never the file, its name or any cell; the file of a preview waits in Redis for at most 30 minutes under a random token) | `import_jobs` (audited); Redis `curriculum-import:*` | A history of imports (Slice 1.25; the screen is Slice 1.26) | Until an administrator removes it |
| External IDs: the institution's own identifier of a phase, module, session or objective | `external_id` columns | Matching rows of a later Excel import to the items they update (Slice 1.25) | With the item |
| Intentional repeats: a framework item a programme teaches in many sessions on purpose, with a short reason typed by a coordinator (no personal data expected; the author is recorded as for all audited data) | `intended_repeats` (audited) | Leaving spiral-curriculum items out of the report on items taught in many sessions (Slice 1.24a) | Until a coordinator removes the mark (soft delete) |
| Gold sets: objective wording and framework item codes with a coverage and depth, typed by a person into an Excel workbook and imported (the workbook itself is read in memory and never stored) | `gold_sets`, `gold_cases`, `gold_links` (audited) | Marking the AI's mapping against an answer key (Slice 1.19) | Until an administrator deletes the gold set (soft delete; its runs go with it from the lists) |
| What the AI answered for each gold objective (item codes, coverage, depth, confidence) and the shortlist it was shown | `eval_runs.results`; the calls themselves in `ai_run_calls` (runs of type `evaluation`) | Working out precision, recall and kappa at any threshold without asking the AI again (Slice 1.19) | The run row: kept with its gold set. The call record: as the prompt (cleared after `AI_CALL_RETENTION_DAYS`) |
| Objectives proposed from a study guide: the wording, the domain, a quote of at most 400 characters from the guide, who decided and when | `objective_proposals` | Letting a person accept or reject each one (Slice 1.18) | Kept after the decision, so the same wording is not proposed again; deleted with its module |
| The uploader's confirmation that the guide holds no real patient information (user, time, text version, SHA-256 and size of the file) | audit log, operation `ai.study_guide_confirmation` | Proof that the confirmation was asked for and given (ADR 042) | As the audit log |
| Provider choice, addresses, budgets, local-only mode | `ai_settings`, `ai_provider_configs` | Configuration | Kept; changes are in the audit log with the acting admin |

How a bulk-accepted mapping link was accepted (`mapping_links.accept_method`) records no person beyond the existing reviewer and audit columns. The server also logs, at start, a warning when `SECRETS_ENCRYPTION_KEYS` is missing in production (no personal data).

Logs of AI calls hold run ids, user ids, the provider name, token counts, timings and the number of
findings of a refusal. Never a prompt, an answer, a name, an address or a key.

## Embeddings

Optional and off by default (ADR 044, [Embeddings](../operations/embeddings.md)). When an administrator turns
them on, objective text and framework item text (title and description) is sent to the
**embeddings server that runs on your own server or private network**, which returns a vector of
384 numbers. The address must be local; a public address is refused. The privacy guard's detectors
look at each text first; unlike a call to an AI provider, **a text they flag is still sent** to
this local server (it never leaves the installation and is already stored), and it is listed on the
objective quality page (kinds only, never the value) so the wording gets fixed.

| Data | Where | Purpose | Retention |
|---|---|---|---|
| A vector of each live objective and framework item, and a hash of its wording | `embeddings` | Finding near-duplicate objectives, and meaning-based search and the AI shortlist later | Rebuilt from the text and removed with a sweep (`embed-all`) once the item is deleted or retired; a vector can leak some meaning of the text, so it follows the database's access and backup rules and is **not exported**. If the text held personal information, so does the vector in a diffuse form: fix the wording and the vector is replaced |
| Pairs of close objectives of one version, with their similarity | `objective_similarities` | Showing near-duplicates on the objective card and in the quality check | Replaced whenever either objective is saved; deleted with the objectives |
| Whether the embeddings server answers (a short-lived flag) | Redis key `embeddings:ready` | Not asking again on every page | 30 seconds |

The server downloads the model (about 470 MB) from huggingface.co the first time it starts. That
request carries no curriculum text and no personal data; it can be avoided by copying the model into
the volume ([Embeddings](../operations/embeddings.md#a-server-without-internet-access)). Logs of the
embedding jobs hold ids and counts only (how many were embedded, unchanged, removed or flagged), never a text or a
vector.

## Redis (temporary)

| Data | Purpose | Retention |
|---|---|---|
| Session: hashed token, user id, creation time | Keeping people signed in | Sliding `SESSION_EXPIRE_HOURS` (default 24) after last use; removed on sign-out, password change and deactivation |
| Rate-limit counters keyed by a hash of the client IP address or email address | Throttling sign-in and reset attempts | 15 minutes |
| Rate-limit counter keyed by a hash of the user id (live objective quality check) | Stopping runaway requests while someone types | 1 minute |
| Rate-limit counter keyed by a hash of the user id (framework pack preview) | Stopping runaway uploads | 1 minute |
| Checked framework pack file (`pack-import:<random token>`): the file text and the id of the user who uploaded it. A pack describes frameworks and holds no personal data unless someone puts it there | Confirming an import without uploading the file again | 30 minutes, removed once imported |
| Rate-limit counter keyed by a hash of the user id (AI "Test connection" button) | Stopping repeated test calls to a paid provider | 1 minute |
| Rate-limit counter keyed by a hash of the user id (AI help with objective wording) | Stopping runaway paid calls | 1 minute |
| Rate-limit counter keyed by a hash of the user id (search, 120 a minute) | Stopping runaway searches | 1 minute |
| Rate-limit counter keyed by a hash of the user id (study-guide upload) | Stopping runaway uploads | 1 minute |
| Password reset token (hashed) and the user id | Reset links | `PASSWORD_RESET_TOKEN_MINUTES` (default 60), single use |
| SSO sign-in state (nonce, PKCE verifier, return path) | Completing an SSO sign-in | 10 minutes, single use |
| Queued job messages, e.g. "send reset email to <address>" | Sending email in the background | Until processed, usually seconds |

## Logs

| Log | Personal information | Retention |
|---|---|---|
| Caddy access log | Client IP address, user agent, requested address (SSO codes redacted; **a search text is part of the address** of a search request, so it is in this log like any address, and nowhere else: the application neither stores nor logs it) | Docker log rotation: 5 files of 10 MB per service (configured in `docker-compose.yml`) |
| API and worker logs | User ids (never email addresses, names, passwords or tokens) | As above |

Copies of logs shipped to a central log system follow that system's retention.

## Backups

Database backups (`deploy/backup.sh`) contain everything in the database table above.
They are kept for `BACKUP_KEEP_DAYS` (default 14) on the server, plus whatever the
institution's off-site backup keeps. A person's deletion reaches backups only when those
backups expire.

## Sent outside Curriculum in Context

| Recipient | What | When |
|---|---|---|
| The institution's SMTP server | Recipient email address, name, reset link | Password reset and "password changed" emails |
| The institution's identity provider | The sign-in request; the provider returns subject id, email and name | SSO sign-in |
| The embeddings server (optional, on your own server or network) | Objective and framework item text; nothing leaves the installation | When an objective is saved and when `embed-all` runs. Nothing is sent while embeddings are off (the default) |
| huggingface.co (only the embeddings server, only on its first start) | A request for the model files; no curriculum text | Once, unless the model is copied in by hand |
| AI provider (optional, chosen by an administrator) | Curriculum text only, never personal information (the privacy guard refuses it); the API key in a header; for the "Test connection" button a fixed test sentence | When an AI feature runs, and when an administrator presses "Test connection". Nothing is sent while AI is off (the default) |

If an AI provider outside South Africa is configured, curriculum text (not personal
information) is transferred abroad. The admin AI settings screen warns the administrator and
requires an acknowledgement before the provider can be chosen; it is recorded with who and when and
stops covering the provider when its address or location changes. Local-only mode blocks every
provider that is not on this server or network. Which providers process text outside South Africa is
stated by the administrator (Anthropic is always treated as outside).

## Rights of data subjects

| Right | How, today |
|---|---|
| Access (section 23) | Users see their own details on the Account page. An admin can export a user's records through the API (`GET /api/v1/users/{id}`, `/role-assignments`, `audit-log?actor_id=`). |
| Correction (section 24) | Admins can change the display name; email changes are not available yet. |
| Deletion (section 24) | Deactivation stops all access at once. Removing an account and anonymising its authorship is supported by the database (authorship and audit actor are cleared) but has no admin function yet. |

A self-service export and a deletion function are planned for Phase 1 (brief section 9).
