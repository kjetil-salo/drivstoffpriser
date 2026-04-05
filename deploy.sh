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

kjor_tester() {
    echo "[test] Kjører backend-tester..."

    if [ -f ".venv/bin/pytest" ]; then
        PYTEST=".venv/bin/pytest"
    else
        PYTEST="pytest"
    fi

    $PYTEST tests/test_db.py tests/test_auth.py tests/test_api.py tests/test_admin.py -q --tb=short

    echo "[test] Kjører Playwright-tester..."
    npx playwright test --reporter=line

    echo "[test] Alle tester OK."
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

bekreft_staging() {
    echo ""
    echo "ADVARSEL: Du er i ferd med å deploye til PRODUKSJON."
    echo "Har du testet endringene på staging (port 3003)?"
    read -r -p "Skriv 'ja' for å fortsette: " svar
    if [ "$svar" != "ja" ]; then
        echo "Deploy avbrutt."
        exit 1
    fi
}

case "${1:-}" in
    prod)
        kjor_tester
        bekreft_staging
        deploy_pi "prod" "docker-compose.yml" "~/drivstoffpriser"
        ;;
    staging)
        kjor_tester
        deploy_pi "staging" "docker-compose.staging.yml" "~/drivstoffpriser-staging"
        echo ""
        echo "[staging] Test på http://raspberrypi:3003 — deploy til prod med: ./deploy.sh prod"
        ;;
    fly)
        kjor_tester
        bekreft_staging
        deploy_fly
        ;;
    all)
        kjor_tester
        bekreft_staging
        deploy_pi "prod" "docker-compose.yml" "~/drivstoffpriser"
        deploy_fly
        ;;
    *)
        usage
        ;;
esac
