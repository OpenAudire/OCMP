# Backup and restore

All Curriculum in Context data lives in the PostgreSQL database. Three scripts in `deploy/` back it up,
check a backup and restore it. They use `pg_dump` and `pg_restore` inside the `db`
container, so nothing extra needs installing on the server.

| What | Where | Backed up by |
|---|---|---|
| Curriculum, frameworks, mappings, accounts, roles, audit log | `db` volume | `backup.sh` |
| Secrets and settings | `deploy/.env` | you: keep a copy in a secrets store |
| Own certificate, local overrides | `deploy/caddy/`, `deploy/docker-compose.override.yml` | you, if you use them |
| Sessions, rate limits, job queue | `redis` volume | not needed: losing it only signs people out |
| Let's Encrypt certificates | `caddy_data` volume | not needed: Caddy requests new ones |

## Make a backup

```bash
cd /opt/ocmp/deploy
./backup.sh
```

The script writes `backups/ocmp-<date>T<time>Z.dump` (compressed `pg_dump` custom
format), checks that the file is complete, and deletes backups older than 14 days. The
site stays available while it runs.

- Another directory: `./backup.sh /srv/backups/ocmp` (or set `BACKUP_DIR`).
- Keep backups longer: `BACKUP_KEEP_DAYS=30 ./backup.sh`; `0` keeps all of them.

Backup files contain personal data (names and email addresses of staff) and the whole
curriculum. They are created readable by their owner only; store copies with the same
care as the server itself.

## Schedule backups

Run the backup every night and copy the files off the server. With cron, as a user who
may run Docker (`crontab -e`):

```cron
# Curriculum in Context database backup, every day at 02:30; output goes to the system log
30 2 * * * /opt/ocmp/deploy/backup.sh 2>&1 | logger -t ocmp-backup
```

Read the results with `journalctl -t ocmp-backup` (or in `/var/log/syslog`).

A backup that stays on the same server does not protect against losing the server. Copy
`deploy/backups/` to other storage after the backup, for example with your institution's
backup agent or `rsync`, and keep at least one copy off site.

## Test a backup

A backup is only useful if it restores. Test one regularly, at least monthly and after
every upgrade:

```bash
./restore-test.sh backups/ocmp-20261025T023000Z.dump
```

The script restores the file into a scratch database (`ocmp_restore_test`) next to the
live one, prints the schema version and the number of rows in the main tables, and drops
the scratch database again. The live data is not touched. Compare the numbers with what
you expect, for example the number of modules in your programmes.

## Restore

Restoring **replaces all data** with the content of the backup and signs everyone out.
Changes made after the backup are lost.

```bash
cd /opt/ocmp/deploy
./restore.sh backups/ocmp-20261025T023000Z.dump
```

The script checks the file, asks you to type `RESTORE`, then:

1. restores the backup into a side database (`ocmp_restoring`) while Curriculum in Context keeps running;
   if this fails, for example because the file is damaged, it stops here and the live
   data is unchanged,
2. stops the `api` and `worker` services (users see an error page for a few seconds),
3. replaces the live database with the restored one,
4. clears Redis (sessions, rate limits and queued jobs),
5. starts Curriculum in Context again; the `migrate` service updates the schema if the backup came from an
   older version.

Add `--yes` to skip the question, for example in scripted recovery tests. The database
server needs free disk space for a second copy of the data while the restore runs.

### Restore on a new server

1. [Install](install.md) Curriculum in Context on the new server up to and including step 4, using the
   **same `.env`** as the old server (copy it from your secrets store).
2. Check out the same Curriculum in Context version as the old server, or a newer one.
3. Start the stack with `docker compose up -d --build --wait`. Do not run the setup wizard.
4. Copy the backup file to the server and run `./restore.sh <file>`.
5. Point the DNS name at the new server.

A backup can only be restored into the same or a newer Curriculum in Context version: migrations upgrade
the schema but never downgrade it.
