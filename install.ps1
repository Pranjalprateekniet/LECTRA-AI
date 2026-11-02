# ==============================================================================
# Revision RAG — Automated One-Command Installation Script (Windows PowerShell)
# ==============================================================================
# Installs and validates all prerequisites, virtual environment, dependencies,
# knowledge-base assets, and configuration.
#
# Usage:
#   .\install.ps1
# ==============================================================================

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[INSTALL] $Message" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "[SUCCESS] $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "[WARNING] $Message" -ForegroundColor Yellow
}

function Write-Err {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "==============================================================================" -ForegroundColor White
Write-Host "              Revision RAG — One-Command Installation System                  " -ForegroundColor White
Write-Host "==============================================================================" -ForegroundColor White
Write-Host ""

# ------------------------------------------------------------------------------
# 1. Operating System & Architecture Detection
# ------------------------------------------------------------------------------
$Arch = $env:PROCESSOR_ARCHITECTURE
Write-Step "Detected platform: Windows ($Arch)"

# ------------------------------------------------------------------------------
# 2. Prerequisite Checks: Python 3.12+ and Node.js 20+
# ------------------------------------------------------------------------------
Write-Step "Checking required system prerequisites..."

# 2.1 Python Check
$PythonBin = $null
$PythonCandidates = @("python", "py", "python3.12", "python3")

foreach ($cand in $PythonCandidates) {
    $cmd = Get-Command $cand -ErrorAction SilentlyContinue
    if ($cmd) {
        try {
            $isMatch = & $cand -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)"
            if ($LASTEXITCODE -eq 0) {
                $PythonBin = $cand
                break
            }
        } catch {
            # Continue checking candidates
        }
    }
}

if (-not $PythonBin) {
    Write-Err "Python 3.12 or newer is required, but was not found on your system."
    Write-Host ""
    Write-Host "Please install Python 3.12+:"
    Write-Host "  winget install Python.Python.3.12"
    Write-Host "  Or download from: https://www.python.org/downloads/"
    Write-Host "  (Ensure 'Add Python to PATH' is checked during installation)"
    exit 1
}

$PyVersion = & $PythonBin -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"
Write-Success "Found Python: $PythonBin ($PyVersion)"

# 2.2 Node.js & npm Check
$NodeCmd = Get-Command node -ErrorAction SilentlyContinue
if (-not $NodeCmd) {
    Write-Err "Node.js is required for the frontend UI, but was not found."
    Write-Host ""
    Write-Host "Please install Node.js 20 LTS or newer:"
    Write-Host "  winget install OpenJS.NodeJS.LTS"
    Write-Host "  Or download from: https://nodejs.org/"
    exit 1
}

$NodeVer = & node -v
$NodeMajor = [int]($NodeVer.TrimStart('v').Split('.')[0])
if ($NodeMajor -lt 20) {
    Write-Err "Node.js version 20+ is required (found $NodeVer). Please upgrade Node.js."
    exit 1
}

$NpmCmd = Get-Command npm -ErrorAction SilentlyContinue
if (-not $NpmCmd) {
    Write-Err "npm is required, but was not found. Please install npm alongside Node.js."
    exit 1
}

$NpmVer = & npm -v
Write-Success "Found Node.js: $NodeVer and npm: $NpmVer"

# ------------------------------------------------------------------------------
# 3. Create Runtime Directories
# ------------------------------------------------------------------------------
Write-Step "Creating persistent runtime directories..."
$Dirs = @("data", "data\artifacts", "data\temp_audio", "data\models", "data\knowledge_base")
foreach ($dir in $Dirs) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}
Write-Success "Runtime directories initialized."

# ------------------------------------------------------------------------------
# 4. Verify Distributed Knowledge-Base Assets
# ------------------------------------------------------------------------------
Write-Step "Verifying pre-indexed knowledge base assets..."
$ArchiveFile = "data\knowledge_base\chunks_7000.jsonl.gz"
$ManifestFile = "data\knowledge_base\manifest.json"
$SeedDb = "data\knowledge_base\student_revision_rag.db"

$MissingAssets = $false
foreach ($asset in @($ArchiveFile, $ManifestFile, $SeedDb)) {
    if (-not (Test-Path $asset)) {
        Write-Err "Missing required distribution asset: $asset"
        $MissingAssets = $true
    }
}

if ($MissingAssets) {
    Write-Err "One or more distribution assets are missing from the repository."
    Write-Host "Please ensure you have cloned the repository with all Git LFS / data files."
    exit 1
}

# Verify SHA-256 Checksum using Python
& $PythonBin -c @"
import hashlib, json, sys
from pathlib import Path

manifest_path = Path('data/knowledge_base/manifest.json')
archive_path = Path('data/knowledge_base/chunks_7000.jsonl.gz')

try:
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
    expected_sha = manifest.get('archive_sha256')

    h = hashlib.sha256()
    with open(archive_path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    actual_sha = h.hexdigest()

    if actual_sha != expected_sha:
        print(f'Checksum mismatch for {archive_path.name}:', file=sys.stderr)
        print(f'  Expected: {expected_sha}', file=sys.stderr)
        print(f'  Actual:   {actual_sha}', file=sys.stderr)
        sys.exit(1)
except Exception as e:
    print(f'Failed to verify knowledge base archive: {e}', file=sys.stderr)
    sys.exit(1)
"@

if ($LASTEXITCODE -ne 0) {
    Write-Err "Knowledge base archive checksum validation failed."
    exit 1
}
Write-Success "Knowledge base assets verified (7,000 vectors, SHA-256 validated)."

# ------------------------------------------------------------------------------
# 5. Setup Python Virtual Environment (.venv)
# ------------------------------------------------------------------------------
Write-Step "Setting up Python virtual environment in .venv..."

$UseUv = $false
if (Get-Command uv -ErrorAction SilentlyContinue) {
    $UseUv = $true
    Write-Step "Using 'uv' for high-speed package management."
}

if (-not (Test-Path ".venv")) {
    if ($UseUv) {
        & uv venv .venv --python $PythonBin
    } else {
        & $PythonBin -m venv .venv
    }
    Write-Success "Virtual environment created at .venv."
} else {
    Write-Step "Existing virtual environment found at .venv."
}

$VenvPy = ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPy)) {
    Write-Err "Python executable not found at $VenvPy."
    exit 1
}

# ------------------------------------------------------------------------------
# 6. Install Python Dependencies
# ------------------------------------------------------------------------------
Write-Step "Checking and installing Python packages (core and backend)..."

$PackagesInstalled = $false
try {
    & $VenvPy -c "import lectra_core, lectra_backend" 2>$null
    if ($LASTEXITCODE -eq 0) {
        $PackagesInstalled = $true
    }
} catch {
    $PackagesInstalled = $false
}

if ($PackagesInstalled) {
    Write-Success "Python packages (core and backend) are already installed."
} else {
    if ($UseUv) {
        & uv pip install --python $VenvPy -e core -e backend
    } else {
        & $VenvPy -m pip install -e core -e backend --quiet
    }
    Write-Success "Python dependencies installed successfully."
}

# ------------------------------------------------------------------------------
# 7. Install Frontend Dependencies
# ------------------------------------------------------------------------------
Write-Step "Checking and installing Next.js frontend dependencies..."
if (Test-Path "frontend") {
    $NextPkg = "frontend\node_modules\next\package.json"
    if (Test-Path $NextPkg) {
        Write-Success "Frontend packages are already installed."
    } else {
        Push-Location frontend
        try {
            & npm install --silent
        } finally {
            Pop-Location
        }
        Write-Success "Frontend dependencies installed successfully."
    }
} else {
    Write-Err "Frontend directory not found at .\frontend."
    exit 1
}

# ------------------------------------------------------------------------------
# 8. Environment Configuration (.env) and Groq API Key
# ------------------------------------------------------------------------------
Write-Step "Checking environment configuration..."

if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Success "Created .env configuration from .env.example."
    } else {
        Write-Err ".env.example template not found."
        exit 1
    }
} else {
    Write-Step "Existing .env file preserved."
}

# Check current GROQ_API_KEY
$CurrentGroqKey = & $VenvPy -c @"
from pathlib import Path
p = Path('.env')
key = ''
if p.exists():
    for line in p.read_text(encoding='utf-8').splitlines():
        if line.strip().startswith('GROQ_API_KEY=') and not line.strip().startswith('#'):
            key = line.strip().split('=', 1)[1].strip().strip('\'\"')
            break
print(key)
"@

$NeedKey = $false
if ([string]::IsNullOrWhiteSpace($CurrentGroqKey) -or $CurrentGroqKey -eq "your_groq_api_key_here") {
    $NeedKey = $true
}

if ($NeedKey) {
    Write-Host ""
    Write-Host "------------------------------------------------------------------------------" -ForegroundColor White
    Write-Host "                        Groq API Key Setup                                    " -ForegroundColor White
    Write-Host "------------------------------------------------------------------------------" -ForegroundColor White
    Write-Host "Revision RAG uses Groq exclusively for local grounded revision answers."
    Write-Host "You can get a free Groq API key at: https://console.groq.com/keys"
    Write-Host ""

    $EnteredKey = Read-Host "Enter your Groq API key (starts with gsk_)"
    $EnteredKey = $EnteredKey.Trim()

    if (-not [string]::IsNullOrWhiteSpace($EnteredKey) -and $EnteredKey -ne "your_groq_api_key_here") {
        & $VenvPy -c @"
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
"@ $EnteredKey
        Write-Success "Groq API key safely saved to .env."
    } else {
        Write-Warn "No API key was entered. You will need to add it manually to .env before starting."
    }
} else {
    Write-Success "Valid GROQ_API_KEY configuration detected."
}

# ------------------------------------------------------------------------------
# 9. Perform Preflight Verification
# ------------------------------------------------------------------------------
Write-Step "Running system and preflight validation..."

$ActiveKey = & $VenvPy -c @"
from pathlib import Path
p = Path('.env')
key = ''
if p.exists():
    for l in p.read_text(encoding='utf-8').splitlines():
        if l.strip().startswith('GROQ_API_KEY=') and not l.strip().startswith('#'):
            key = l.strip().split('=', 1)[1].strip().strip('\'\"')
print(key)
"@

if (-not [string]::IsNullOrWhiteSpace($ActiveKey) -and $ActiveKey -ne "your_groq_api_key_here") {
    & $VenvPy run.py --check-only
    if ($LASTEXITCODE -eq 0) {
        Write-Success "All preflight verification checks passed."
    }
} else {
    Write-Step "Skipping active runner check because GROQ_API_KEY is not yet configured."
}

# ------------------------------------------------------------------------------
# 10. Completion Banner
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "==============================================================================" -ForegroundColor Green
Write-Host "                   Revision RAG Installation Complete!                        " -ForegroundColor Green
Write-Host "==============================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "To start the application, simply run:"
Write-Host "  .\start.ps1" -ForegroundColor Yellow
Write-Host ""
Write-Host "Then open your web browser at:"
Write-Host "  👉 http://localhost:3000" -ForegroundColor Cyan
Write-Host ""
Write-Host "To add more YouTube playlists later:"
Write-Host "  1. Switch APP_MODE to DEVELOPER in .env"
Write-Host "  2. Access the ingestion admin panel at: http://localhost:3000/admin"
Write-Host ""
