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

AI prompts and responses (`ai_run_calls`, Phase 1) contain curriculum text only. Personal
information must never be sent to an AI provider; the brief requires a privacy guard that
enforces this in code before any provider is called. Stored prompts and responses are
cleared after `AI_CALL_RETENTION_DAYS` (default 365).

## Redis (temporary)

| Data | Purpose | Retention |
|---|---|---|
| Session: hashed token, user id, creation time | Keeping people signed in | Sliding `SESSION_EXPIRE_HOURS` (default 24) after last use; removed on sign-out, password change and deactivation |
| Rate-limit counters keyed by a hash of the client IP address or email address | Throttling sign-in and reset attempts | 15 minutes |
| Rate-limit counter keyed by a hash of the user id (live objective quality check) | Stopping runaway requests while someone types | 1 minute |
| Rate-limit counter keyed by a hash of the user id (framework pack preview) | Stopping runaway uploads | 1 minute |
| Checked framework pack file (`pack-import:<random token>`): the file text and the id of the user who uploaded it. A pack describes frameworks and holds no personal data unless someone puts it there | Confirming an import without uploading the file again | 30 minutes, removed once imported |
| Password reset token (hashed) and the user id | Reset links | `PASSWORD_RESET_TOKEN_MINUTES` (default 60), single use |
| SSO sign-in state (nonce, PKCE verifier, return path) | Completing an SSO sign-in | 10 minutes, single use |
| Queued job messages, e.g. "send reset email to <address>" | Sending email in the background | Until processed, usually seconds |

## Logs

| Log | Personal information | Retention |
|---|---|---|
| Caddy access log | Client IP address, user agent, requested address (SSO codes redacted) | Docker log rotation: 5 files of 10 MB per service (configured in `docker-compose.yml`) |
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
| AI provider (Phase 1, optional) | Curriculum text only, never personal information | When AI features are used |

If an AI provider outside South Africa is configured, curriculum text (not personal
information) is transferred abroad; Curriculum in Context will warn the administrator (brief section 9).

## Rights of data subjects

| Right | How, today |
|---|---|
| Access (section 23) | Users see their own details on the Account page. An admin can export a user's records through the API (`GET /api/v1/users/{id}`, `/role-assignments`, `audit-log?actor_id=`). |
| Correction (section 24) | Admins can change the display name; email changes are not available yet. |
| Deletion (section 24) | Deactivation stops all access at once. Removing an account and anonymising its authorship is supported by the database (authorship and audit actor are cleared) but has no admin function yet. |

A self-service export and a deletion function are planned for Phase 1 (brief section 9).
