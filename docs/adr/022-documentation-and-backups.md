# ADR 022: Documentation Site and Backups

## Status

Accepted

## Context

The brief (sections 5, 7 and 12) asks for a MkDocs Material site published to GitHub
Pages, with an install guide good enough to set up a fresh Linux server, upgrade and
backup/restore guides with a `pg_dump` script, admin basics, and a documented backup
schedule and restore test. Checked on 2026-10-25: MkDocs 1.6.1 and Material for MkDocs
9.8.0 are the current releases on PyPI. Material 9.8 announces its end of life on
5 May 2027 (critical and security fixes until then) and names Zensical, by the same team,
as its successor; Zensical is at 0.0.72 and builds this site's `mkdocs.yml` unchanged in
strict mode with no issues.

## Decision

### Site
- MkDocs with Material, as the brief asks, pinned in `docs/requirements.txt` and installed
  in its own virtual environment (`.venv-docs`), not mixed with the backend's
  dependencies. Move to Zensical before May 2027, once it has a stable release; it reads
  the same `mkdocs.yml`.
- `mkdocs.yml` at the repository root with `docs_dir: docs`, so ADRs, `PROGRESS.md` and
  the brief are part of the site and links between them are checked.
- Only YAML without Python tags (no `!!python/name`), so the `check-yaml` pre-commit hook
  accepts the file.
- `mkdocs build --strict` runs in CI on every push and pull request: broken links and
  missing pages fail the build. A separate workflow publishes `main` to GitHub Pages.
- Structure: Operations (install, configuration, upgrade, backup and restore) for server
  operators; Administration (admin basics, users and roles, SSO) for platform admins; user
  guides per role follow with the Phase 1 screens. Until admin screens exist, the guides
  show the API calls with `curl` and `jq`.

### Backups
- `deploy/backup.sh` runs `pg_dump --format=custom` inside the `db` container, so the dump
  always matches the server version and nothing is installed on the host. The file is
  written as `.partial`, checked with `pg_restore --list` and only then renamed;
  permissions are owner-only; old dumps are removed after `BACKUP_KEEP_DAYS` (14).
- `deploy/restore-test.sh` restores a dump into a scratch database in the same container
  and prints the schema version and row counts, without touching live data.
- `deploy/restore.sh` restores into a side database first (one transaction), so a damaged
  file never leaves an empty database: `pg_restore --list` alone passes a dump that is
  cut off in its data section, as tested. Only then does it stop `api` and `worker`, drop
  the live database, rename the side database, flush Redis (sessions, limits and queued
  jobs belong to the replaced data) and start the stack, so `migrate` upgrades older
  backups.
- Redis and Caddy volumes are not backed up: losing them only signs people out or
  re-issues certificates. `.env` is not in the dump; operators keep it in a secrets store.
- Scripts are POSIX `sh` and honour `COMPOSE_PROJECT_NAME`/`COMPOSE_FILE`.

### Local deployment changes
- `deploy/caddy/*.caddy` files are imported into the site block (an empty match is not an
  error), for example `tls` with an institution's own certificate on servers Let's
  Encrypt cannot reach. `deploy/docker-compose.override.yml` holds other local changes.
  Both are git-ignored, so upgrades with `git checkout` keep them.

### Readiness
- `/ready` returns HTTP 503 when the database or Redis is down (it returned 200 with
  `not_ready` in the body), so monitoring can rely on the status code.

## Consequences

- GitHub Pages must be enabled for the repository with "GitHub Actions" as the source,
  and the repository variable `PAGES_ENABLED=true` set; until then the Docs workflow only
  builds the site and skips publishing (changed in Slice 1.1; it used to fail).
- Restoring needs the same or a newer OCMP version than the backup (migrations only go
  forward).
- The install guide links to Docker's official installation pages instead of copying
  their commands, which change over time.
