#!/bin/sh
# Back up the OCMP database to a pg_dump file (custom format, compressed).
#
# Usage: ./backup.sh [backup-directory]
#
# The directory defaults to $BACKUP_DIR, else ./backups next to this script.
# Backups older than $BACKUP_KEEP_DAYS days (default 14, 0 keeps all) are removed.
# The .env file is not included: keep a copy of it somewhere safe as well.
set -eu

cd "$(dirname "$0")"
backup_dir=${1:-${BACKUP_DIR:-./backups}}
keep_days=${BACKUP_KEEP_DAYS:-14}

# Dumps contain all curriculum and account data: readable by the owner only.
umask 077
mkdir -p "$backup_dir"

target="$backup_dir/ocmp-$(date -u +%Y%m%dT%H%M%SZ).dump"
partial="$target.partial"
trap 'rm -f "$partial"' EXIT

# The database name and user come from the db container's own environment.
docker compose exec -T db sh -c \
    'pg_dump --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --format=custom' \
    > "$partial"

# A failed pg_dump stops the script above; this also checks the file is readable.
docker compose exec -T db pg_restore --list < "$partial" > /dev/null

mv "$partial" "$target"
echo "Backup written to $target ($(du -h "$target" | cut -f1))"

if [ "$keep_days" -gt 0 ]; then
    find "$backup_dir" -type f -name 'ocmp-*.dump' -mtime +"$keep_days" -print -delete \
        | sed 's/^/Removed old backup /'
fi
