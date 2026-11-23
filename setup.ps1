<#
.SYNOPSIS
    AI Explainer & Whiteboard Sketch Studio — 1-Click Setup for Windows (PowerShell)

.EXAMPLE
    .\setup.ps1
    .\setup.ps1 -Start
#>
param(
    [switch]$Start,
    [int]$Port = 8090
)

$ErrorActionPreference = "Stop"
$RepoDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoDir

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "  AI Explainer & Whiteboard Sketch Studio — 1-Click Windows Setup" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan

# 1. Check Python 3.11+
$PythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $PythonCmd) {
    Write-Host "[ERROR] Python 3.11/3.12 not found. Install it with:" -ForegroundColor Red
    Write-Host "        winget install Python.Python.3.12" -ForegroundColor Yellow
    exit 1
}
$PyVer = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
Write-Host "[1/5] Using Python $PyVer ($($PythonCmd.Source))" -ForegroundColor Green

# 2. Check FFmpeg
$FfmpegCmd = Get-Command ffmpeg -ErrorAction SilentlyContinue
if ($FfmpegCmd) {
    Write-Host "[2/5] FFmpeg found: $($FfmpegCmd.Source)" -ForegroundColor Green
} else {
    Write-Host "[2/5] FFmpeg not found on PATH. Installing via winget (or run: winget install Gyan.FFmpeg)..." -ForegroundColor Yellow
    $Winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($Winget) {
        winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
    } else {
        Write-Host "[WARN] Please install FFmpeg manually and add it to PATH." -ForegroundColor Yellow
    }
}

# 3. Create .venv & install Studio dependencies
Write-Host "[3/5] Setting up virtual environment (.venv) and installing dependencies..." -ForegroundColor Cyan
if (-not (Test-Path "$RepoDir\.venv")) {
    & python -m venv "$RepoDir\.venv"
}
$VenvPy  = "$RepoDir\.venv\Scripts\python.exe"
$VenvPip = "$RepoDir\.venv\Scripts\pip.exe"
& $VenvPy -m pip install --upgrade pip -q
& $VenvPip install -r "$RepoDir\pipeline\requirements.txt"

# 4. Create .env from template if missing
if (-not (Test-Path "$RepoDir\.env") -and (Test-Path "$RepoDir\.env.example")) {
    Copy-Item "$RepoDir\.env.example" "$RepoDir\.env"
    Write-Host "[4/5] Created .env from .env.example (defaults to 127.0.0.1)" -ForegroundColor Green
} else {
    Write-Host "[4/5] Using existing .env configuration" -ForegroundColor Green
}

# 5. Self-check & Local AI Services Status
Write-Host "[5/5] Verifying Studio installation..." -ForegroundColor Cyan
& $VenvPy -c "from pipeline.web_ui import app; from pipeline.config import PipelineConfig; print('      Studio import OK! Default GPU host:', PipelineConfig().gpu_host)"

$GpuHost = if ($env:SKETCH_GPU_HOST) { $env:SKETCH_GPU_HOST } else { "127.0.0.1" }
function Test-ServiceUrl($Label, $Url) {
    try {
        $null = Invoke-WebRequest -Uri $Url -TimeoutSec 2 -UseBasicParsing
        Write-Host "      [ONLINE]  $Label ($Url)" -ForegroundColor Green
    } catch {
        Write-Host "      [OFFLINE] $Label ($Url)" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Local AI Services Check (host: $GpuHost):" -ForegroundColor Cyan
Test-ServiceUrl "Ollama (Director & Vision QA)" "http://${GpuHost}:11434/api/tags"
Test-ServiceUrl "ComfyUI (Qwen-Image)"          "http://${GpuHost}:8188/system_stats"
Test-ServiceUrl "Chatterbox TTS (Voiceover)"    "http://${GpuHost}:8004/health"

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "  Setup Complete!" -ForegroundColor Green
Write-Host "  Start the Web Studio anytime with:" -ForegroundColor White
Write-Host "    .\.venv\Scripts\Activate.ps1; uvicorn pipeline.web_ui:app --host 0.0.0.0 --port $Port" -ForegroundColor Yellow
Write-Host "  Then open: http://localhost:$Port" -ForegroundColor White
Write-Host "======================================================================" -ForegroundColor Cyan

if ($Start) {
    Write-Host "Launching Web Studio UI on http://localhost:$Port ..." -ForegroundColor Green
    Start-Process "http://localhost:$Port"
    & "$RepoDir\.venv\Scripts\uvicorn.exe" pipeline.web_ui:app --host 0.0.0.0 --port $Port
}
