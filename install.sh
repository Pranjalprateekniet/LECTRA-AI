#!/usr/bin/env bash
# ==============================================================================
# Revision RAG — Automated One-Command Installation Script (Linux & macOS)
# ==============================================================================
# Installs and validates all prerequisites, virtual environment, dependencies,
# knowledge-base assets, and configuration.
#
# Usage:
#   ./install.sh
# ==============================================================================

set -e

# Terminal colors
BLUE='\033[1;34m'
GREEN='\033[1;32m'
YELLOW='\033[1;33m'
RED='\033[1;31m'
BOLD='\033[1m'
NC='\033[0m' # No Color

log_step() {
    echo -e "${BLUE}[INSTALL]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_err() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

# Resolve project root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${BOLD}==============================================================================${NC}"
echo -e "${BOLD}              Revision RAG — One-Command Installation System                  ${NC}"
echo -e "${BOLD}==============================================================================${NC}"
echo ""

# ------------------------------------------------------------------------------
# 1. Operating System & Architecture Detection
# ------------------------------------------------------------------------------
OS="$(uname -s)"
ARCH="$(uname -m)"
log_step "Detected platform: ${BOLD}${OS} (${ARCH})${NC}"

case "$OS" in
    Linux*)     PLATFORM="linux" ;;
    Darwin*)    PLATFORM="macos" ;;
    *)          PLATFORM="unknown" ;;
esac

if [ "$PLATFORM" = "unknown" ]; then
    log_warn "Unrecognized operating system ($OS). Installation will proceed using POSIX standards."
fi

# ------------------------------------------------------------------------------
# 2. Prerequisite Checks: Python 3.12+ and Node.js 20+
# ------------------------------------------------------------------------------
log_step "Checking required system prerequisites..."

# 2.1 Python Check
PYTHON_BIN=""
for candidate in python3.12 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        if "$candidate" -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" 2>/dev/null; then
            PYTHON_BIN="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    log_err "Python 3.12 or newer is required, but was not found on your system."
    echo ""
    echo "Please install Python 3.12+ using your package manager:"
    if [ "$PLATFORM" = "macos" ]; then
        echo "  brew install python@3.12"
    elif command -v apt-get >/dev/null 2>&1; then
        echo "  sudo apt update && sudo apt install -y python3.12 python3.12-venv python3-pip"
    elif command -v dnf >/dev/null 2>&1; then
        echo "  sudo dnf install -y python3.12"
    else
        echo "  Visit: https://www.python.org/downloads/"
    fi
    exit 1
fi

PY_VERSION="$("$PYTHON_BIN" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')")"
log_success "Found Python: ${BOLD}$PYTHON_BIN ($PY_VERSION)${NC}"

# 2.2 Node.js & npm Check
if ! command -v node >/dev/null 2>&1; then
    log_err "Node.js is required for the frontend UI, but was not found."
    echo ""
    echo "Please install Node.js 20 LTS or newer:"
    if [ "$PLATFORM" = "macos" ]; then
        echo "  brew install node@20"
    elif command -v apt-get >/dev/null 2>&1; then
        echo "  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -"
        echo "  sudo apt install -y nodejs"
    else
        echo "  Visit: https://nodejs.org/"
    fi
    exit 1
fi

NODE_MAJOR="$(node -v | sed 's/^v//' | cut -d. -f1)"
if [ "$NODE_MAJOR" -lt 20 ]; then
    log_err "Node.js version 20+ is required (found $(node -v)). Please upgrade Node.js."
    exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
    log_err "npm is required, but was not found. Please install npm alongside Node.js."
    exit 1
fi

log_success "Found Node.js: ${BOLD}$(node -v)${NC} and npm: ${BOLD}$(npm -v)${NC}"

# ------------------------------------------------------------------------------
# 3. Create Runtime Directories
# ------------------------------------------------------------------------------
log_step "Creating persistent runtime directories..."
mkdir -p data data/artifacts data/temp_audio data/models data/knowledge_base
log_success "Runtime directories initialized."

# ------------------------------------------------------------------------------
# 4. Verify Distributed Knowledge-Base Assets
# ------------------------------------------------------------------------------
log_step "Verifying pre-indexed knowledge base assets..."
KB_DIR="data/knowledge_base"
ARCHIVE_FILE="$KB_DIR/chunks_7000.jsonl.gz"
MANIFEST_FILE="$KB_DIR/manifest.json"
SEED_DB="$KB_DIR/student_revision_rag.db"

MISSING_ASSETS=0
for asset in "$ARCHIVE_FILE" "$MANIFEST_FILE" "$SEED_DB"; do
    if [ ! -f "$asset" ]; then
        log_err "Missing required distribution asset: $asset"
        MISSING_ASSETS=1
    fi
done

if [ "$MISSING_ASSETS" -ne 0 ]; then
    log_err "One or more distribution assets are missing from the repository."
    echo "Please ensure you have cloned the repository with all Git LFS / data files."
    exit 1
fi

# Validate SHA-256 Checksum using Python
"$PYTHON_BIN" - << 'EOF'
import hashlib, json, sys
from pathlib import Path

manifest_path = Path("data/knowledge_base/manifest.json")
archive_path = Path("data/knowledge_base/chunks_7000.jsonl.gz")

try:
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    expected_sha = manifest.get("archive_sha256")

    h = hashlib.sha256()
    with open(archive_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    actual_sha = h.hexdigest()

    if actual_sha != expected_sha:
        print(f"Checksum mismatch for {archive_path.name}:", file=sys.stderr)
        print(f"  Expected: {expected_sha}", file=sys.stderr)
        print(f"  Actual:   {actual_sha}", file=sys.stderr)
        sys.exit(1)
except Exception as e:
    print(f"Failed to verify knowledge base archive: {e}", file=sys.stderr)
    sys.exit(1)
EOF

log_success "Knowledge base assets verified (7,000 vectors, SHA-256 validated)."

# ------------------------------------------------------------------------------
# 5. Setup Python Virtual Environment (.venv)
# ------------------------------------------------------------------------------
log_step "Setting up Python virtual environment in .venv..."

# Detect if uv is available
USE_UV=0
if command -v uv >/dev/null 2>&1; then
    USE_UV=1
    log_step "Using 'uv' for high-speed package management."
fi

if [ ! -d ".venv" ]; then
    if [ "$USE_UV" -eq 1 ]; then
        uv venv .venv --python "$PYTHON_BIN"
    else
        "$PYTHON_BIN" -m venv .venv || {
            log_err "Failed to create virtual environment using '$PYTHON_BIN -m venv .venv'."
            if command -v apt-get >/dev/null 2>&1; then
                echo "On Debian/Ubuntu, you may need to install python3-venv:"
                echo "  sudo apt install -y python3-venv python3.12-venv"
            fi
            exit 1
        }
    fi
    log_success "Virtual environment created at .venv."
else
    log_step "Existing virtual environment found at .venv."
fi

VENV_PY=".venv/bin/python"
if [ ! -f "$VENV_PY" ]; then
    log_err "Python executable not found at $VENV_PY."
    exit 1
fi

# ------------------------------------------------------------------------------
# 6. Install Python Dependencies
# ------------------------------------------------------------------------------
log_step "Checking and installing Python packages (core and backend)..."

if "$VENV_PY" -c "import lectra_core, lectra_backend" >/dev/null 2>&1; then
    log_success "Python packages (core and backend) are already installed."
else
    if [ "$USE_UV" -eq 1 ]; then
        uv pip install --python "$VENV_PY" -e core -e backend
    else
        "$VENV_PY" -m pip install -e core -e backend --quiet
    fi
    log_success "Python dependencies installed successfully."
fi

# ------------------------------------------------------------------------------
# 7. Install Frontend Dependencies
# ------------------------------------------------------------------------------
log_step "Checking and installing Next.js frontend dependencies..."
if [ -d "frontend" ]; then
    if [ -d "frontend/node_modules" ] && [ -f "frontend/node_modules/next/package.json" ]; then
        log_success "Frontend packages are already installed."
    else
        (cd frontend && npm install --silent)
        log_success "Frontend dependencies installed successfully."
    fi
else
    log_err "Frontend directory not found at ./frontend."
    exit 1
fi

# ------------------------------------------------------------------------------
# 8. Environment Configuration (.env) and Groq API Key
# ------------------------------------------------------------------------------
log_step "Checking environment configuration..."

if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        log_success "Created .env configuration from .env.example."
    else
        log_err ".env.example template not found."
        exit 1
    fi
else
    log_step "Existing .env file preserved."
fi

# Check current GROQ_API_KEY
CURRENT_GROQ_KEY="$("$VENV_PY" -c "
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

NEED_KEY=0
if [ -z "$CURRENT_GROQ_KEY" ] || [ "$CURRENT_GROQ_KEY" = "your_groq_api_key_here" ]; then
    NEED_KEY=1
fi

if [ "$NEED_KEY" -eq 1 ]; then
    echo ""
    echo -e "${BOLD}------------------------------------------------------------------------------${NC}"
    echo -e "${BOLD}                        Groq API Key Setup                                    ${NC}"
    echo -e "${BOLD}------------------------------------------------------------------------------${NC}"
    echo "Revision RAG uses Groq exclusively for local grounded revision answers."
    echo "You can get a free Groq API key at: https://console.groq.com/keys"
    echo ""

    if [ -t 0 ]; then
        # Interactive shell
        read -s -p "Enter your Groq API key (starts with gsk_): " ENTERED_KEY
        echo ""
        ENTERED_KEY="$(echo "$ENTERED_KEY" | tr -d '[:space:]')"

        if [ -n "$ENTERED_KEY" ] && [ "$ENTERED_KEY" != "your_groq_api_key_here" ]; then
            "$VENV_PY" -c "
import sys
from pathlib import Path
p = Path('.env')
lines = p.read_text(encoding='utf-8').splitlines()
out = []
replaced = False
for line in lines:
    if line.strip().startswith('GROQ_API_KEY='):
        out.append(f'GROQ_API_KEY={sys.argv[1]}')
        replaced = True
    else:
        out.append(line)
if not replaced:
    out.append(f'GROQ_API_KEY={sys.argv[1]}')
p.write_text('\n'.join(out) + '\n', encoding='utf-8')
" "$ENTERED_KEY"
            log_success "Groq API key safely saved to .env."
        else
            log_warn "No API key was entered. You will need to add it manually to .env before starting."
        fi
    else
        log_warn "Non-interactive session detected. Please set your GROQ_API_KEY in .env before running ./start.sh."
    fi
else
    log_success "Valid GROQ_API_KEY configuration detected."
fi

# ------------------------------------------------------------------------------
# 9. Perform Preflight Verification
# ------------------------------------------------------------------------------
log_step "Running system and preflight validation..."

# Check if GROQ_API_KEY is configured before running check-only
ACTIVE_KEY="$("$VENV_PY" -c "
from pathlib import Path
p = Path('.env')
key = ''
if p.exists():
    for l in p.read_text(encoding='utf-8').splitlines():
        if l.strip().startswith('GROQ_API_KEY=') and not l.strip().startswith('#'):
            key = l.strip().split('=', 1)[1].strip().strip('\'\"')
print(key)
")"

if [ -n "$ACTIVE_KEY" ] && [ "$ACTIVE_KEY" != "your_groq_api_key_here" ]; then
    "$VENV_PY" run.py --check-only
    log_success "All preflight verification checks passed."
else
    log_step "Skipping active runner check because GROQ_API_KEY is not yet configured."
fi

# ------------------------------------------------------------------------------
# 10. Completion Banner
# ------------------------------------------------------------------------------
echo ""
echo -e "${GREEN}${BOLD}==============================================================================${NC}"
echo -e "${GREEN}${BOLD}                   Revision RAG Installation Complete!                        ${NC}"
echo -e "${GREEN}${BOLD}==============================================================================${NC}"
echo ""
echo "To start the application, simply run:"
echo -e "  ${BOLD}./start.sh${NC}"
echo ""
echo "Then open your web browser at:"
echo -e "  👉 ${BOLD}http://localhost:3000${NC}"
echo ""
echo "To add more YouTube playlists later:"
echo "  1. Switch APP_MODE to DEVELOPER in .env"
echo "  2. Access the ingestion admin panel at: http://localhost:3000/admin"
echo ""
