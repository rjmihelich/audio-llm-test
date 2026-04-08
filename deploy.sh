#!/usr/bin/env bash
# ------------------------------------------------------------------
# deploy.sh — One-command deploy for Audio LLM Test
#
# Usage (on the server):
#   ./deploy.sh          # pull + smart restart
#   ./deploy.sh --full   # pull + full rebuild everything
#   ./deploy.sh --status # just show container status
#
# What it does:
#   1. git pull
#   2. Detect what changed
#   3. Rebuild Docker images only if Dockerfile / deps changed
#   4. Restart containers that need it
#   5. Run DB migrations if any
#   6. Print status
# ------------------------------------------------------------------
set -euo pipefail

cd "$(dirname "$0")"

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${CYAN}▸${NC} $*"; }
ok()   { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC} $*"; }
err()  { echo -e "${RED}✗${NC} $*"; }

# ---- Status-only mode ----
if [[ "${1:-}" == "--status" ]]; then
    echo -e "\n${BOLD}Container Status${NC}"
    docker compose ps
    echo ""
    docker compose logs --tail=5 backend 2>/dev/null || true
    exit 0
fi

# ---- Purge results mode ----
if [[ "${1:-}" == "--purge-results" ]]; then
    echo -e "\n${BOLD}═══ Purging test results & runs ═══${NC}"
    warn "This will delete ALL test_results, test_runs, and degraded audio files."
    warn "Test suites, cases, speech samples, and corpus entries are preserved."
    read -p "Type 'yes' to confirm: " CONFIRM
    if [[ "$CONFIRM" != "yes" ]]; then
        err "Aborted."
        exit 1
    fi
    log "Deleting test_results..."
    docker compose exec -T db psql -U postgres -d audio_llm_test -c "DELETE FROM test_results;"
    log "Deleting test_runs..."
    docker compose exec -T db psql -U postgres -d audio_llm_test -c "DELETE FROM test_runs;"
    log "Cleaning degraded audio files..."
    docker compose exec -T worker rm -rf /app/storage/audio/degraded/ 2>/dev/null || true
    log "Flushing worker state from Redis..."
    docker compose exec -T redis redis-cli DEL worker:activity worker:heartbeat worker:recent_errors worker:error_budget watchdog:report 2>/dev/null || true
    docker compose exec -T redis redis-cli DEL worker:log 2>/dev/null || true
    ok "Done! All results purged. Suites, cases, and speech samples intact."
    echo ""
    docker compose exec -T db psql -U postgres -d audio_llm_test -c "SELECT 'test_results' as tbl, COUNT(*) FROM test_results UNION ALL SELECT 'test_runs', COUNT(*) FROM test_runs UNION ALL SELECT 'test_suites', COUNT(*) FROM test_suites UNION ALL SELECT 'test_cases', COUNT(*) FROM test_cases UNION ALL SELECT 'speech_samples', COUNT(*) FROM speech_samples;"
    exit 0
fi

FORCE_REBUILD=false
if [[ "${1:-}" == "--full" ]]; then
    FORCE_REBUILD=true
    warn "Full rebuild requested"
fi

# ---- 1. Git pull ----
echo -e "\n${BOLD}═══ Pulling latest code ═══${NC}"
BEFORE=$(git rev-parse HEAD)
git pull --ff-only
AFTER=$(git rev-parse HEAD)

if [[ "$BEFORE" == "$AFTER" && "$FORCE_REBUILD" == "false" ]]; then
    ok "Already up to date ($BEFORE)"
    echo -e "\n${BOLD}Container Status${NC}"
    docker compose ps
    exit 0
fi

# Show what changed
CHANGED_FILES=$(git diff --name-only "$BEFORE" "$AFTER" 2>/dev/null || echo "")
if [[ -n "$CHANGED_FILES" ]]; then
    log "Changed files:"
    echo "$CHANGED_FILES" | sed 's/^/    /'
fi

# ---- 2. Detect what needs rebuilding ----
REBUILD_BACKEND=false
REBUILD_FRONTEND=false
RESTART_BACKEND=false
RESTART_WORKER=false
RESTART_FRONTEND=false
RUN_MIGRATIONS=false

if [[ "$FORCE_REBUILD" == "true" ]]; then
    REBUILD_BACKEND=true
    REBUILD_FRONTEND=true
else
    # Backend image rebuild needed?
    if echo "$CHANGED_FILES" | grep -qE '^(Dockerfile|pyproject\.toml|setup\.py|setup\.cfg|requirements.*\.txt)'; then
        REBUILD_BACKEND=true
        log "Backend dependencies or Dockerfile changed → rebuild"
    fi

    # Frontend image rebuild needed?
    if echo "$CHANGED_FILES" | grep -qE '^frontend/(Dockerfile|package\.json|package-lock\.json)'; then
        REBUILD_FRONTEND=true
        log "Frontend dependencies or Dockerfile changed → rebuild"
    fi

    # Backend code changed? (volume mounted, just restart)
    if echo "$CHANGED_FILES" | grep -qE '^backend/'; then
        RESTART_BACKEND=true
        RESTART_WORKER=true
    fi

    # Frontend code changed? (volume mounted, vite hot-reloads but restart to be safe)
    if echo "$CHANGED_FILES" | grep -qE '^frontend/'; then
        RESTART_FRONTEND=true
    fi

    # Docker compose changed?
    if echo "$CHANGED_FILES" | grep -qE '^docker-compose'; then
        REBUILD_BACKEND=true
        REBUILD_FRONTEND=true
        log "docker-compose.yml changed → recreate all"
    fi

    # Alembic migrations?
    if echo "$CHANGED_FILES" | grep -qE '^(alembic|backend/app/models)/'; then
        RUN_MIGRATIONS=true
    fi
fi

# ---- 3. Rebuild images if needed ----
if [[ "$REBUILD_BACKEND" == "true" ]]; then
    echo -e "\n${BOLD}═══ Rebuilding backend image ═══${NC}"
    docker compose build --no-cache backend worker
    ok "Backend image rebuilt"
fi

if [[ "$REBUILD_FRONTEND" == "true" ]]; then
    echo -e "\n${BOLD}═══ Rebuilding frontend image ═══${NC}"
    docker compose build --no-cache frontend
    ok "Frontend image rebuilt"
fi

# ---- 4. Restart / recreate containers ----
echo -e "\n${BOLD}═══ Restarting services ═══${NC}"

if [[ "$REBUILD_BACKEND" == "true" || "$REBUILD_FRONTEND" == "true" ]]; then
    # Recreate to pick up new images
    docker compose up -d --force-recreate
    ok "All containers recreated"
else
    SERVICES_TO_RESTART=""
    [[ "$RESTART_BACKEND" == "true" ]]  && SERVICES_TO_RESTART="$SERVICES_TO_RESTART backend"
    [[ "$RESTART_WORKER" == "true" ]]   && SERVICES_TO_RESTART="$SERVICES_TO_RESTART worker"
    [[ "$RESTART_FRONTEND" == "true" ]] && SERVICES_TO_RESTART="$SERVICES_TO_RESTART frontend"

    if [[ -n "$SERVICES_TO_RESTART" ]]; then
        docker compose restart $SERVICES_TO_RESTART
        ok "Restarted:$SERVICES_TO_RESTART"
    else
        warn "No services needed restart"
    fi
fi

# ---- 5. Run migrations if needed ----
if [[ "$RUN_MIGRATIONS" == "true" ]]; then
    echo -e "\n${BOLD}═══ Running DB migrations ═══${NC}"
    docker compose exec -T backend alembic upgrade head 2>/dev/null && ok "Migrations applied" || warn "No alembic config or already up to date"
fi

# ---- 6. Health check ----
echo -e "\n${BOLD}═══ Checking health ═══${NC}"
sleep 3

# Quick health ping
if curl -sf http://localhost:8000/api/ping > /dev/null 2>&1; then
    ok "Backend API responding"
else
    warn "Backend not responding yet (may still be starting)"
fi

if curl -sf http://localhost:5173 > /dev/null 2>&1; then
    ok "Frontend responding"
else
    warn "Frontend not responding yet (may still be starting)"
fi

# ---- 7. Summary ----
echo -e "\n${BOLD}═══ Deploy complete ═══${NC}"
echo -e "  Commit: ${CYAN}$(git rev-parse --short HEAD)${NC} — $(git log -1 --format='%s')"
echo ""
docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || docker compose ps
echo ""
