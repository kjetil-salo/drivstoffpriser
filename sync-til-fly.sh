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

# Rydd opp eventuell gammel tempfil
rm -f "$TMP_BACKUP"

# Sikker backup via python3 sqlite3.backup() — håndterer WAL-modus korrekt
python3 - <<EOF
import sqlite3, sys
src = sqlite3.connect('$DB_PATH')
dst = sqlite3.connect('$TMP_BACKUP')
src.backup(dst)
src.close()
dst.close()

# Integritetssjekk av backup
conn = sqlite3.connect('$TMP_BACKUP')
ok = conn.execute('PRAGMA integrity_check').fetchone()[0]
conn.close()
if ok != 'ok':
    print(f'Backup feilet integritetssjekk: {ok}', file=sys.stderr)
    sys.exit(1)
print(f'Backup OK, integritetssjekk: {ok}')
EOF

# Vekk Fly.io-instansen og vent til den er klar
echo "Vekker Fly.io..."
curl -s -o /dev/null --max-time 30 "https://drivstoffpriser.fly.dev/health" || true

echo "Venter til Fly.io er klar..."
READY=0
for attempt in $(seq 1 18); do
    if curl -fsS -o /dev/null --max-time 10 "https://drivstoffpriser.fly.dev/health"; then
        READY=1
        echo "Fly.io er klar etter $attempt sjekk(er)."
        break
    fi
    sleep 5
done

if [ "$READY" -ne 1 ]; then
    echo "Fly.io ble ikke klar i tide" >&2
    rm -f "$TMP_BACKUP"
    exit 1
fi

# Send til Fly.io (maks 90 sek, 3 forsøk ved feil)
HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' \
    --max-time 90 \
    --retry 3 \
    --retry-delay 15 \
    --retry-all-errors \
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
