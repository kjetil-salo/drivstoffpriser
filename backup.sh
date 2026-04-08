#!/bin/bash
# Backup av drivstoff.db fra Docker-volumet.
# Kjøres som cron-jobb: 0 3 * * * /home/kjetil/drivstoffpriser/backup.sh
set -e

DB_PATH="/var/lib/docker/volumes/drivstoffpriser_drivstoff-data/_data/drivstoff.db"
BACKUP_DIR="/home/kjetil/backups/drivstoffpriser"
DAGLIG_DIR="$BACKUP_DIR/daglig"
UKENTLIG_DIR="$BACKUP_DIR/ukentlig"

mkdir -p "$DAGLIG_DIR" "$UKENTLIG_DIR"

DATO=$(date +%Y-%m-%d)
UKEDAG=$(date +%u)  # 1=mandag, 7=søndag

# Sikker backup via sqlite3 (håndterer WAL/locks korrekt)
DAGLIG_FIL="$DAGLIG_DIR/drivstoff-$DATO.db"
sudo sqlite3 "$DB_PATH" ".backup '$DAGLIG_FIL'"

# Ukentlig kopi på søndager
if [ "$UKEDAG" = "7" ]; then
    cp "$DAGLIG_FIL" "$UKENTLIG_DIR/drivstoff-$DATO.db"
fi

# Rydd opp: behold 7 daglige og 4 ukentlige
ls -t "$DAGLIG_DIR"/drivstoff-*.db 2>/dev/null | tail -n +8 | xargs -r rm
ls -t "$UKENTLIG_DIR"/drivstoff-*.db 2>/dev/null | tail -n +5 | xargs -r rm

# Last opp til Cloudflare R2
rclone copy "$DAGLIG_FIL" r2:drivstoffpriser-backup/daglig/ \
    --s3-no-check-bucket \
    --log-level ERROR \
    2>> /tmp/drivstoff-backup.log

# Rydd opp i R2: slett filer eldre enn 30 dager
rclone delete r2:drivstoffpriser-backup/daglig/ \
    --min-age 30d \
    --s3-no-check-bucket \
    2>> /tmp/drivstoff-backup.log

echo "$(date): Backup OK ($DAGLIG_FIL)"
