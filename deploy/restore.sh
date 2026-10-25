#!/bin/sh
# Restore the OCMP database from a backup made by backup.sh.
#
# Usage: ./restore.sh <backup-file> [--yes]
#
# Replaces ALL data in the database and signs everyone out. The backup is first
# restored into a side database, so a damaged file leaves the live data as it
# was. Only then are the api and worker stopped and the databases swapped; the
# stack starts again and the migrate service brings an older backup up to date.
# The single-quoted commands expand $POSTGRES_* inside the db container, on purpose.
# shellcheck disable=SC2016
set -eu

if [ $# -lt 1 ]; then
    echo "Usage: $0 <backup-file> [--yes]" >&2
    exit 2
fi
file=$1
confirmed=${2:-}

# Resolve the file before changing to the compose directory.
case $file in
    /*) ;;
    *) file="$PWD/$file" ;;
esac
if [ ! -f "$file" ]; then
    echo "No such file: $file" >&2
    exit 1
fi

cd "$(dirname "$0")"
restoring=ocmp_restoring

# Runs a command in the db container, which knows the database user and name;
# RESTORING names the side database.
in_db() {
    docker compose exec -T -e RESTORING="$restoring" db sh -c "$1"
}

docker compose up -d --wait db redis
if ! docker compose exec -T db pg_restore --list < "$file" > /dev/null; then
    echo "$file is not a readable pg_dump file; nothing was changed." >&2
    exit 1
fi

if [ "$confirmed" != "--yes" ]; then
    echo "This replaces ALL data in the OCMP database with $file"
    echo "and signs everyone out. Type RESTORE to continue."
    read -r answer
    if [ "$answer" != "RESTORE" ]; then
        echo "Cancelled; nothing was changed."
        exit 1
    fi
fi

echo "Restoring $file into a side database..."
in_db 'PGOPTIONS="-c client_min_messages=warning" \
       dropdb --username="$POSTGRES_USER" --force --if-exists "$RESTORING" \
       && createdb --username="$POSTGRES_USER" "$RESTORING"'
if ! in_db 'pg_restore --username="$POSTGRES_USER" --dbname="$RESTORING" \
            --no-owner --no-acl --single-transaction --exit-on-error' < "$file"; then
    in_db 'dropdb --username="$POSTGRES_USER" --force --if-exists "$RESTORING"'
    echo "The backup could not be restored; the live data was not changed." >&2
    exit 1
fi

echo "Stopping api and worker..."
docker compose stop api worker

echo "Replacing the live database..."
in_db 'dropdb --username="$POSTGRES_USER" --force "$POSTGRES_DB" \
       && psql --username="$POSTGRES_USER" --dbname=postgres --no-psqlrc -v ON_ERROR_STOP=1 \
               -c "ALTER DATABASE \"$RESTORING\" RENAME TO \"$POSTGRES_DB\""'

# Sessions, sign-in limits and queued jobs belong to the replaced data.
echo "Clearing sessions and queued jobs..."
docker compose exec -T redis redis-cli FLUSHALL > /dev/null

echo "Starting OCMP (migrations run first)..."
docker compose up -d --wait
echo "Restore complete."
