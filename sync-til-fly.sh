#!/bin/bash
# Synkroniser SQLite-database til Fly.io backup-instans
# Cron: 0 */6 * * * /home/kjetil/drivstoffpriser/sync-til-fly.sh

set -euo pipefail

FLY_URL="https://drivstoffpriser.fly.dev/api/sync-db"
SYNC_KEY="${SYNC_KEY:-}"
DB_PATH="/var/lib/docker/volumes/drivstoffpriser_drivstoff-data/_data/drivstoff.db"
TMP_BACKUP="/tmp/drivstoff-sync.db"

if [ -z "$SYNC_KEY" ]; then
    echo "SYNC_KEY ikke satt" >&2
    exit 1
fi

# Sikker backup med sqlite3 .backup (unngår korrupt kopi ved skriving)
sqlite3 "$DB_PATH" ".backup '$TMP_BACKUP'"

# Send til Fly.io
HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' \
    -X PUT \
    -H "X-Sync-Key: $SYNC_KEY" \
    -H "Content-Type: application/octet-stream" \
    --data-binary "@$TMP_BACKUP" \
    "$FLY_URL")

rm -f "$TMP_BACKUP"

if [ "$HTTP_CODE" = "200" ]; then
    echo "Sync OK (HTTP $HTTP_CODE)"
else
    echo "Sync feilet (HTTP $HTTP_CODE)" >&2
    exit 1
fi
