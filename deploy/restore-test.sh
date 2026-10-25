#!/bin/sh
# Check that a backup restores, without touching the live data.
#
# Usage: ./restore-test.sh <backup-file>
#
# Restores into a scratch database (ocmp_restore_test) in the running db
# container, prints the schema version and row counts, then drops it again.
# The single-quoted commands expand $POSTGRES_* inside the db container, on purpose.
# shellcheck disable=SC2016
set -eu

if [ $# -ne 1 ]; then
    echo "Usage: $0 <backup-file>" >&2
    exit 2
fi
file=$1
case $file in
    /*) ;;
    *) file="$PWD/$file" ;;
esac
if [ ! -f "$file" ]; then
    echo "No such file: $file" >&2
    exit 1
fi

cd "$(dirname "$0")"
scratch=ocmp_restore_test

in_db() {
    docker compose exec -T -e SCRATCH="$scratch" db sh -c "$1"
}

cleanup() {
    in_db 'PGOPTIONS="-c client_min_messages=warning" dropdb --username="$POSTGRES_USER" --force --if-exists "$SCRATCH"'
}
trap cleanup EXIT

cleanup
in_db 'createdb --username="$POSTGRES_USER" "$SCRATCH"'
in_db 'pg_restore --username="$POSTGRES_USER" --dbname="$SCRATCH" \
       --no-owner --no-acl --single-transaction --exit-on-error' < "$file"

in_db 'psql --username="$POSTGRES_USER" --dbname="$SCRATCH" --no-psqlrc -v ON_ERROR_STOP=1' <<'SQL'
SELECT version_num AS schema_version FROM alembic_version;
SELECT 'institutions' AS table_name, count(*) AS row_count FROM institutions
UNION ALL SELECT 'users', count(*) FROM users
UNION ALL SELECT 'programmes', count(*) FROM programmes
UNION ALL SELECT 'modules', count(*) FROM modules
UNION ALL SELECT 'learning_events', count(*) FROM learning_events
UNION ALL SELECT 'objectives', count(*) FROM objectives
UNION ALL SELECT 'framework_items', count(*) FROM framework_items
UNION ALL SELECT 'mapping_links', count(*) FROM mapping_links
UNION ALL SELECT 'audit_log', count(*) FROM audit_log;
SQL

echo "Restore test passed: $file restores cleanly."
