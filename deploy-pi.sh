#!/bin/bash
# Deploy drivstoffpriser til Raspberry Pi
set -e

PI="kjetil@100.76.35.106"
REMOTE_DIR="~/drivstoffpriser"

echo "Kopierer filer til Pi..."
rsync -av --exclude-from='.rsyncignore' ./ "$PI:$REMOTE_DIR/"

echo "Bygger og starter container på Pi..."
ssh "$PI" "cd $REMOTE_DIR && docker compose up -d --build"

echo "Ferdig! Drivstoffpriser kjører på Pi (port 3002)"
