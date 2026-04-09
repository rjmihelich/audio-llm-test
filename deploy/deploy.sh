#!/usr/bin/env bash
# Universal zero-downtime deploy script for Docker Compose apps on this server.
# Usage: deploy.sh <app-directory> [service...]
#
# Examples:
#   deploy.sh /home/ryan/server/apps/audio-llm-test
#   deploy.sh /home/ryan/server/apps/llm-explorer
#   deploy.sh /home/ryan/server/apps/audio-llm-test backend frontend
#
# How it works:
#   1. git pull (if app dir is a git repo)
#   2. docker compose build --no-cache (while old containers still serve traffic)
#   3. docker compose up -d (brief restart window minimized to startup time only)
#   4. Wait for all health-checked containers to report "healthy"
#   5. Exit 0 on success, 1 on timeout/unhealthy
#
# To add zero-downtime to any app:
#   Add a healthcheck: block to its docker-compose.yml backend/app service,
#   pointing at a readiness endpoint (e.g. GET /api/health/ready -> 200).
#   The deploy script will wait until Docker reports that container as healthy.
#   See audio-llm-test/docker-compose.yml for a working example.

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()  { echo -e "${BLUE}[deploy]${NC} $*"; }
ok()   { echo -e "${GREEN}[deploy]${NC} $*"; }
warn() { echo -e "${YELLOW}[deploy]${NC} $*"; }
err()  { echo -e "${RED}[deploy]${NC} $*" >&2; }

# ── Args ──────────────────────────────────────────────────────────────────────
if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <app-directory> [service...]" >&2
    exit 1
fi

APP_DIR="$(realpath "$1")"
shift
SERVICES=("$@")  # optional: specific services to rebuild/restart

if [[ ! -d "$APP_DIR" ]]; then
    err "Directory not found: $APP_DIR"
    exit 1
fi

cd "$APP_DIR"
log "Deploying $(basename "$APP_DIR") from $APP_DIR"

# ── Step 1: git pull ──────────────────────────────────────────────────────────
if [[ -d .git ]]; then
    log "Pulling latest code..."
    git pull --ff-only || {
        warn "git pull --ff-only failed (diverged?). Trying regular pull..."
        git pull || { err "git pull failed — aborting"; exit 1; }
    }
    log "Now at: $(git log --oneline -1)"
else
    warn "Not a git repo, skipping git pull"
fi

# ── Step 2: Build (old containers still running — no downtime yet) ────────────
log "Building images (old containers still serving traffic)..."
if [[ ${#SERVICES[@]} -gt 0 ]]; then
    docker compose build --no-cache "${SERVICES[@]}"
else
    docker compose build --no-cache
fi
ok "Build complete."

# ── Step 3: Start new containers (brief restart window starts here) ───────────
log "Starting new containers..."
if [[ ${#SERVICES[@]} -gt 0 ]]; then
    docker compose up -d "${SERVICES[@]}"
else
    docker compose up -d
fi
log "Containers started. Waiting for health checks..."

# ── Step 4: Wait for health checks to pass ───────────────────────────────────
HEALTH_TIMEOUT=180  # max seconds to wait for any single container
POLL_INTERVAL=5

wait_healthy() {
    local container="$1"
    local start=$SECONDS

    log "Waiting for $container to be healthy (max ${HEALTH_TIMEOUT}s)..."
    while true; do
        local status
        status=$(docker inspect \
            --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' \
            "$container" 2>/dev/null || echo "missing")

        case "$status" in
            healthy)
                echo ""
                ok "$container is healthy ✓"
                return 0
                ;;
            no-healthcheck)
                warn "$container has no healthcheck — assuming ready"
                return 0
                ;;
            missing)
                warn "$container not found — may have exited"
                return 1
                ;;
            starting)
                local elapsed=$(( SECONDS - start ))
                echo -ne "\r${YELLOW}[deploy]${NC} $container: starting... ${elapsed}s elapsed"
                ;;
            unhealthy)
                echo ""
                err "$container is unhealthy after $(( SECONDS - start ))s"
                err "Recent logs:"
                docker compose logs --tail=40 "$container" 2>/dev/null || true
                return 1
                ;;
        esac

        local elapsed=$(( SECONDS - start ))
        if (( elapsed >= HEALTH_TIMEOUT )); then
            echo ""
            err "Timed out after ${elapsed}s waiting for $container"
            err "Recent logs:"
            docker compose logs --tail=40 "$container" 2>/dev/null || true
            return 1
        fi
        sleep "$POLL_INTERVAL"
    done
}

# Get all containers for this compose project
CONTAINERS=$(docker compose ps -q 2>/dev/null \
    | xargs -r docker inspect --format='{{.Name}}' 2>/dev/null \
    | sed 's|^/||' \
    || true)

if [[ -z "$CONTAINERS" ]]; then
    warn "No running containers found — check 'docker compose ps'"
else
    FAILED=0
    for container in $CONTAINERS; do
        has_health=$(docker inspect \
            --format='{{if .State.Health}}yes{{else}}no{{end}}' \
            "$container" 2>/dev/null || echo "no")
        if [[ "$has_health" == "yes" ]]; then
            wait_healthy "$container" || FAILED=1
        fi
    done

    if [[ $FAILED -eq 1 ]]; then
        err ""
        err "One or more containers failed to become healthy."
        err "The deploy completed but the app may be degraded."
        err "Run: docker compose -f $APP_DIR/docker-compose.yml ps"
        exit 1
    fi
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
ok "════════════════════════════════════════"
ok " Deploy complete: $(basename "$APP_DIR")"
ok " $(date)"
ok "════════════════════════════════════════"
