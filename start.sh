#!/usr/bin/env bash
# ==============================================================================
# Revision RAG — Application Startup Script (Linux & macOS)
# ==============================================================================
# Verifies installation state and launches the unified Revision RAG runner
# (FastAPI backend + Next.js frontend).
#
# Usage:
#   ./start.sh [--backend-port PORT] [--frontend-port PORT] [--check-only]
# ==============================================================================

set -e

# Terminal colors
BLUE='\033[1;34m'
GREEN='\033[1;32m'
YELLOW='\033[1;33m'
RED='\033[1;31m'
BOLD='\033[1m'
NC='\033[0m' # No Color

log_err() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

# Resolve project root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 1. Verify virtual environment exists
if [ ! -d ".venv" ] || [ ! -f ".venv/bin/python" ]; then
    log_err "Python virtual environment not found at .venv."
    echo ""
    echo "Please run the installation script first:"
    echo "  ./install.sh"
    echo ""
    exit 1
fi

VENV_PY=".venv/bin/python"

# 2. Verify .env exists
if [ ! -f ".env" ]; then
    log_err "Environment configuration file (.env) not found."
    echo ""
    echo "Please run the installation script to initialize your configuration:"
    echo "  ./install.sh"
    echo ""
    exit 1
fi

# 3. Verify GROQ_API_KEY is configured
GROQ_KEY="$("$VENV_PY" -c "
from pathlib import Path
env_path = Path('.env')
key = ''
if env_path.exists():
    for line in env_path.read_text(encoding='utf-8').splitlines():
        if line.strip().startswith('GROQ_API_KEY=') and not line.strip().startswith('#'):
            key = line.strip().split('=', 1)[1].strip().strip('\'\"')
            break
print(key)
")"

if [ -z "$GROQ_KEY" ] || [ "$GROQ_KEY" = "your_groq_api_key_here" ]; then
    log_err "GROQ_API_KEY is not configured in .env."
    echo ""
    echo "Revision RAG uses Groq exclusively for local grounded revision answers."
    echo "1. Get a free API key at: https://console.groq.com/keys"
    echo "2. Add your key to .env:"
    echo "   GROQ_API_KEY=gsk_your_actual_groq_api_key_here"
    echo ""
    echo "Or re-run ./install.sh to configure it interactively."
    echo ""
    exit 1
fi

# 4. Launch unified runner via exec (preserves clean SIGINT / Ctrl+C propagation)
exec "$VENV_PY" run.py "$@"
