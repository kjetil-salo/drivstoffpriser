#!/bin/bash
# Deploy drivstoffpriser til valgt miljø
set -e

PI="kjetil@100.76.35.106"

usage() {
    echo "Bruk: ./deploy.sh <miljø>"
    echo ""
    echo "Miljøer:"
    echo "  prod      Deploy til Pi (port 3002)"
    echo "  staging   Deploy til Pi (port 3003, egen database)"
    echo "  fly       Deploy til Fly.io (backup-instans)"
    echo "  all       Deploy til prod + fly"
    exit 1
}

deploy_pi() {
    local ENV_NAME=$1
    local COMPOSE_FILE=$2
    local REMOTE_DIR=$3

    echo "[$ENV_NAME] Kopierer filer til Pi..."
    rsync -av --exclude-from='.rsyncignore' ./ "$PI:$REMOTE_DIR/"

    echo "[$ENV_NAME] Bygger og starter container på Pi..."
    ssh "$PI" "cd $REMOTE_DIR && docker compose -f $COMPOSE_FILE up -d --build"

    echo "[$ENV_NAME] Ferdig!"
}

deploy_fly() {
    echo "[fly] Deployer til Fly.io..."
    fly deploy
    echo "[fly] Ferdig!"
}

case "${1:-}" in
    prod)
        deploy_pi "prod" "docker-compose.yml" "~/drivstoffpriser"
        ;;
    staging)
        deploy_pi "staging" "docker-compose.staging.yml" "~/drivstoffpriser-staging"
        ;;
    fly)
        deploy_fly
        ;;
    all)
        deploy_pi "prod" "docker-compose.yml" "~/drivstoffpriser"
        deploy_fly
        ;;
    *)
        usage
        ;;
esac
