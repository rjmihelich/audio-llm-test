#!/usr/bin/env bash
# =============================================================================
# Audio LLM Test Platform — Start All Services
# =============================================================================
# Starts backend API, arq worker, and frontend dev server.
# Requires: PostgreSQL and Redis already running (setup.sh handles this).
#
# Usage:
#   ./start.sh          # Start all services
#   ./start.sh stop     # Stop all background services
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

PID_DIR="$PROJECT_DIR/.pids"
mkdir -p "$PID_DIR"

LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

stop_services() {
    echo -e "${YELLOW}Stopping services...${NC}"
    for pidfile in "$PID_DIR"/*.pid; do
        [ -f "$pidfile" ] || continue
        pid=$(cat "$pidfile")
        name=$(basename "$pidfile" .pid)
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            echo -e "  Stopped ${name} (PID $pid)"
        fi
        rm -f "$pidfile"
    done
    echo -e "${GREEN}All services stopped.${NC}"
}

if [ "${1:-}" = "stop" ]; then
    stop_services
    exit 0
fi

# Stop any previously running instances
stop_services 2>/dev/null || true

# Check prerequisites
if ! pg_isready -q 2>/dev/null; then
    echo -e "${RED}PostgreSQL is not running.${NC} Start it first:"
    echo "  macOS:  brew services start postgresql@16"
    echo "  Linux:  sudo systemctl start postgresql"
    echo "  Docker: docker compose up db -d"
    exit 1
fi

if ! redis-cli ping 2>/dev/null | grep -q PONG; then
    echo -e "${RED}Redis is not running.${NC} Start it first:"
    echo "  macOS:  brew services start redis"
    echo "  Linux:  sudo systemctl start redis-server"
    echo "  Docker: docker compose up redis -d"
    exit 1
fi

if [ ! -d ".venv" ]; then
    echo -e "${RED}Python venv not found.${NC} Run ./setup.sh first."
    exit 1
fi

source .venv/bin/activate

echo ""
echo "============================================="
echo "  Audio LLM Test Platform"
echo "============================================="
echo ""

# 1. Backend API
echo -e "${BLUE}Starting backend API...${NC}"
uvicorn backend.app.main:app --reload --port 8000 \
    > "$LOG_DIR/backend.log" 2>&1 &
echo $! > "$PID_DIR/backend.pid"
echo -e "  ${GREEN}Backend${NC}  → http://localhost:8000  (log: logs/backend.log)"

# 2. arq Worker
echo -e "${BLUE}Starting task worker...${NC}"
arq backend.app.execution.worker.WorkerSettings \
    > "$LOG_DIR/worker.log" 2>&1 &
echo $! > "$PID_DIR/worker.pid"
echo -e "  ${GREEN}Worker${NC}   → background  (log: logs/worker.log)"

# 3. Frontend
echo -e "${BLUE}Starting frontend...${NC}"
cd frontend
npm run dev -- --host 2>/dev/null \
    > "$LOG_DIR/frontend.log" 2>&1 &
echo $! > "$PID_DIR/frontend.pid"
cd "$PROJECT_DIR"
echo -e "  ${GREEN}Frontend${NC} → http://localhost:5173  (log: logs/frontend.log)"

# Wait for backend to be ready
echo ""
echo -n "Waiting for backend..."
for i in $(seq 1 20); do
    if curl -s http://localhost:8000/api/health | grep -q ok; then
        echo -e " ${GREEN}ready${NC}"
        break
    fi
    echo -n "."
    sleep 1
done

echo ""
echo -e "${GREEN}All services running!${NC}"
echo ""
echo "  Open: http://localhost:5173"
echo ""
echo "  Stop: ./start.sh stop"
echo "  Logs: tail -f logs/backend.log"
echo ""
