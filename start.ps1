# ==============================================================================
# Revision RAG — Application Startup Script (Windows PowerShell)
# ==============================================================================
# Verifies installation state and launches the unified Revision RAG runner
# (FastAPI backend + Next.js frontend).
#
# Usage:
#   .\start.ps1 [-BackendPort 8000] [-FrontendPort 3000] [-CheckOnly]
# ==============================================================================

$ErrorActionPreference = "Stop"

function Write-Err {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# 1. Verify virtual environment exists
$VenvPy = ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPy)) {
    Write-Err "Python virtual environment not found at .venv."
    Write-Host ""
    Write-Host "Please run the installation script first:"
    Write-Host "  .\install.ps1"
    Write-Host ""
    exit 1
}

# 2. Verify .env exists
if (-not (Test-Path ".env")) {
    Write-Err "Environment configuration file (.env) not found."
    Write-Host ""
    Write-Host "Please run the installation script to initialize your configuration:"
    Write-Host "  .\install.ps1"
    Write-Host ""
    exit 1
}

# 3. Verify GROQ_API_KEY is configured
$GroqKey = & $VenvPy -c @"
from pathlib import Path
env_path = Path('.env')
key = ''
if env_path.exists():
    for line in env_path.read_text(encoding='utf-8').splitlines():
        if line.strip().startswith('GROQ_API_KEY=') and not line.strip().startswith('#'):
            key = line.strip().split('=', 1)[1].strip().strip('\'\"')
            break
print(key)
"@

if ([string]::IsNullOrWhiteSpace($GroqKey) -or $GroqKey -eq "your_groq_api_key_here") {
    Write-Err "GROQ_API_KEY is not configured in .env."
    Write-Host ""
    Write-Host "Revision RAG uses Groq exclusively for local grounded revision answers."
    Write-Host "1. Get a free API key at: https://console.groq.com/keys"
    Write-Host "2. Add your key to .env:"
    Write-Host "   GROQ_API_KEY=gsk_your_actual_groq_api_key_here"
    Write-Host ""
    Write-Host "Or re-run .\install.ps1 to configure it interactively."
    Write-Host ""
    exit 1
}

# 4. Launch unified runner
& $VenvPy run.py @args
exit $LASTEXITCODE
