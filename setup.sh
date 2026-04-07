#!/usr/bin/env bash
# =============================================================================
# Audio LLM Test Platform — One-Command Setup
# =============================================================================
# Usage:
#   chmod +x setup.sh && ./setup.sh
#
# This script installs everything needed to run the platform locally:
#   - Python 3.12 + backend dependencies + faster-whisper
#   - Node.js + frontend dependencies
#   - PostgreSQL + Redis (via Homebrew on macOS, apt on Linux)
#   - Ollama with the Mistral model
#   - Edge TTS (free text-to-speech)
#
# After setup, run:
#   ./start.sh
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
fail()  { echo -e "${RED}[FAIL]${NC}  $*"; exit 1; }

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

echo ""
echo "============================================="
echo "  Audio LLM Test Platform — Setup"
echo "============================================="
echo ""

# ---------------------------------------------------------------------------
# Detect OS
# ---------------------------------------------------------------------------
OS="$(uname -s)"
case "$OS" in
    Darwin) PLATFORM="macos" ;;
    Linux)  PLATFORM="linux" ;;
    *)      fail "Unsupported OS: $OS. This script supports macOS and Linux." ;;
esac
info "Detected platform: $PLATFORM"

# ---------------------------------------------------------------------------
# macOS: Ensure Homebrew is available
# ---------------------------------------------------------------------------
if [ "$PLATFORM" = "macos" ]; then
    if ! command -v brew &>/dev/null; then
        info "Installing Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        # Add brew to path for Apple Silicon
        if [ -f /opt/homebrew/bin/brew ]; then
            eval "$(/opt/homebrew/bin/brew shellenv)"
        fi
    fi
    ok "Homebrew available"
fi

# ---------------------------------------------------------------------------
# 1. Python 3.12
# ---------------------------------------------------------------------------
info "Checking Python..."
PYTHON=""

# Try to find Python 3.12 or 3.11
for candidate in python3.12 python3.11 python3; do
    if command -v "$candidate" &>/dev/null; then
        ver=$("$candidate" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "$major" -eq 3 ] && [ "$minor" -ge 11 ]; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    info "Installing Python 3.12..."
    if [ "$PLATFORM" = "macos" ]; then
        brew install python@3.12
        PYTHON="$(brew --prefix python@3.12)/bin/python3.12"
    else
        sudo apt-get update
        sudo apt-get install -y python3.12 python3.12-venv python3.12-dev
        PYTHON="python3.12"
    fi
fi
ok "Python: $($PYTHON --version)"

# ---------------------------------------------------------------------------
# 2. Node.js (for the frontend)
# ---------------------------------------------------------------------------
info "Checking Node.js..."
if ! command -v node &>/dev/null; then
    info "Installing Node.js..."
    if [ "$PLATFORM" = "macos" ]; then
        brew install node
    else
        # Install via NodeSource
        curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
        sudo apt-get install -y nodejs
    fi
fi
ok "Node: $(node --version)"
ok "npm:  $(npm --version)"

# ---------------------------------------------------------------------------
# 3. PostgreSQL
# ---------------------------------------------------------------------------
info "Checking PostgreSQL..."
if ! command -v psql &>/dev/null; then
    info "Installing PostgreSQL..."
    if [ "$PLATFORM" = "macos" ]; then
        brew install postgresql@16
        brew services start postgresql@16
    else
        sudo apt-get install -y postgresql postgresql-contrib
        sudo systemctl enable postgresql
        sudo systemctl start postgresql
    fi
else
    ok "PostgreSQL already installed"
    # Make sure it's running
    if [ "$PLATFORM" = "macos" ]; then
        brew services start postgresql@16 2>/dev/null || brew services start postgresql 2>/dev/null || true
    else
        sudo systemctl start postgresql 2>/dev/null || true
    fi
fi

# Wait for PostgreSQL to be ready
info "Waiting for PostgreSQL..."
for i in $(seq 1 15); do
    if pg_isready -q 2>/dev/null; then
        break
    fi
    sleep 1
done

if pg_isready -q 2>/dev/null; then
    ok "PostgreSQL is running"
else
    warn "PostgreSQL may not be running. You can also use Docker: docker compose up db -d"
fi

# Create database if it doesn't exist
info "Creating database..."
if [ "$PLATFORM" = "macos" ]; then
    createdb audio_llm_test 2>/dev/null || true
else
    sudo -u postgres createdb audio_llm_test 2>/dev/null || true
    # Ensure current user can connect
    sudo -u postgres psql -c "CREATE USER $(whoami) WITH SUPERUSER;" 2>/dev/null || true
fi
ok "Database: audio_llm_test"

# ---------------------------------------------------------------------------
# 4. Redis
# ---------------------------------------------------------------------------
info "Checking Redis..."
if ! command -v redis-server &>/dev/null; then
    info "Installing Redis..."
    if [ "$PLATFORM" = "macos" ]; then
        brew install redis
        brew services start redis
    else
        sudo apt-get install -y redis-server
        sudo systemctl enable redis-server
        sudo systemctl start redis-server
    fi
else
    ok "Redis already installed"
    if [ "$PLATFORM" = "macos" ]; then
        brew services start redis 2>/dev/null || true
    else
        sudo systemctl start redis-server 2>/dev/null || true
    fi
fi

# Check Redis is responding
if redis-cli ping 2>/dev/null | grep -q PONG; then
    ok "Redis is running"
else
    warn "Redis may not be running. You can also use Docker: docker compose up redis -d"
fi

# ---------------------------------------------------------------------------
# 5. System libraries (for audio processing)
# ---------------------------------------------------------------------------
info "Checking system libraries..."
if [ "$PLATFORM" = "macos" ]; then
    brew install libsndfile 2>/dev/null || true
else
    sudo apt-get install -y libsndfile1 libsndfile1-dev ffmpeg 2>/dev/null || true
fi
ok "Audio libraries installed"

# ---------------------------------------------------------------------------
# 6. Python virtual environment + dependencies
# ---------------------------------------------------------------------------
info "Setting up Python virtual environment..."
if [ ! -d ".venv" ]; then
    $PYTHON -m venv .venv
    info "Created .venv"
fi

source .venv/bin/activate
ok "Activated .venv ($(.venv/bin/python --version))"

info "Installing Python dependencies..."
pip install --upgrade pip setuptools wheel -q

# Install the project with local extras (faster-whisper, edge-tts)
pip install -e ".[whisper-local]" -q
pip install edge-tts -q
pip install faster-whisper -q

ok "Python dependencies installed"

# Pre-download the Whisper base model so first run isn't slow
info "Pre-downloading Whisper model (base, ~150MB)..."
python -c "
from faster_whisper import WhisperModel
model = WhisperModel('base', device='cpu', compute_type='int8')
print('Whisper base model ready')
" 2>/dev/null && ok "Whisper model cached" || warn "Whisper model will download on first use"

# ---------------------------------------------------------------------------
# 7. Frontend dependencies
# ---------------------------------------------------------------------------
info "Installing frontend dependencies..."
cd "$PROJECT_DIR/frontend"
npm install --silent 2>/dev/null
cd "$PROJECT_DIR"
ok "Frontend dependencies installed"

# ---------------------------------------------------------------------------
# 8. Ollama (local LLM)
# ---------------------------------------------------------------------------
info "Checking Ollama..."
if ! command -v ollama &>/dev/null; then
    info "Installing Ollama..."
    if [ "$PLATFORM" = "macos" ]; then
        brew install ollama
    else
        curl -fsSL https://ollama.ai/install.sh | sh
    fi
fi

# Start Ollama if not running
if ! curl -s http://localhost:11434/api/tags &>/dev/null; then
    info "Starting Ollama..."
    if [ "$PLATFORM" = "macos" ]; then
        brew services start ollama 2>/dev/null || (ollama serve &>/dev/null &)
    else
        ollama serve &>/dev/null &
    fi
    sleep 3
fi

# Pull Mistral model if not already available
if ollama list 2>/dev/null | grep -q "mistral"; then
    ok "Ollama: mistral model already available"
else
    info "Pulling Mistral model (~4GB, this may take a few minutes)..."
    ollama pull mistral
    ok "Ollama: mistral model ready"
fi

# ---------------------------------------------------------------------------
# 9. Environment file
# ---------------------------------------------------------------------------
if [ ! -f ".env" ]; then
    info "Creating .env from .env.example..."
    cp .env.example .env
    ok ".env created — edit it to add API keys (optional)"
else
    ok ".env already exists"
fi

# ---------------------------------------------------------------------------
# 10. Create storage directories
# ---------------------------------------------------------------------------
mkdir -p storage/audio storage/results
ok "Storage directories ready"

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo "============================================="
echo -e "  ${GREEN}Setup complete!${NC}"
echo "============================================="
echo ""
echo "  To start the platform:"
echo ""
echo "    ./start.sh"
echo ""
echo "  Or start services manually:"
echo ""
echo "    # Terminal 1 — Backend API"
echo "    source .venv/bin/activate"
echo "    uvicorn backend.app.main:app --reload --port 8000"
echo ""
echo "    # Terminal 2 — Task worker"
echo "    source .venv/bin/activate"
echo "    arq backend.app.execution.worker.WorkerSettings"
echo ""
echo "    # Terminal 3 — Frontend"
echo "    cd frontend && npm run dev"
echo ""
echo "  Then open: http://localhost:5173"
echo ""
echo "  Or use Docker:"
echo "    docker compose up"
echo ""
