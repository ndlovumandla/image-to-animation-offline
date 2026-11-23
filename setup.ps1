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
Write-Host "[1/6] Using Python $PyVer ($($PythonCmd.Source))" -ForegroundColor Green

# 2. Check NVIDIA GPU, Driver & CUDA (nvidia-smi)
$NvidiaSmi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if ($NvidiaSmi) {
    try {
        $GpuInfo = (& nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader | Select-Object -First 1).Trim()
        $SmiHeader = (& nvidia-smi | Select-String "CUDA Version:" | Select-Object -First 1).ToString()
        $CudaVer = if ($SmiHeader -match "CUDA Version:\s*([0-9.]+)") { $Matches[1] } else { "unknown" }
        $VramMiB = [int]((& nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | Select-Object -First 1).Trim())
        Write-Host "[2/6] NVIDIA GPU detected: $GpuInfo (CUDA $CudaVer)" -ForegroundColor Green
        if ($VramMiB -lt 12000) {
            Write-Host "      [WARN] Detected $VramMiB MiB VRAM; 12-16 GB VRAM is recommended for local Qwen-Image + gemma3:12b." -ForegroundColor Yellow
        }
        $NvccCmd = Get-Command nvcc -ErrorAction SilentlyContinue
        if ($NvccCmd) {
            $NvccVer = (& nvcc --version | Select-Object -Last 1).Trim()
            Write-Host "      CUDA Toolkit (nvcc): $NvccVer" -ForegroundColor Green
        } else {
            Write-Host "      [INFO] nvcc toolkit not on PATH (optional - NVIDIA driver + nvidia-smi is sufficient for prebuilt PyTorch/Ollama/ComfyUI)." -ForegroundColor DarkGray
        }
    } catch {
        Write-Host "[2/6] [WARN] nvidia-smi is installed but failed to query GPU. Update/reinstall your NVIDIA driver." -ForegroundColor Yellow
    }
} else {
    Write-Host "[2/6] [WARN] nvidia-smi not found. Install the latest NVIDIA GPU driver for local AI, or set SKETCH_GPU_HOST in .env to a remote GPU server." -ForegroundColor Yellow
}

# 3. Check FFmpeg
$FfmpegCmd = Get-Command ffmpeg -ErrorAction SilentlyContinue
if ($FfmpegCmd) {
    Write-Host "[3/6] FFmpeg found: $($FfmpegCmd.Source)" -ForegroundColor Green
} else {
    Write-Host "[3/6] FFmpeg not found on PATH. Installing via winget (or run: winget install Gyan.FFmpeg)..." -ForegroundColor Yellow
    $Winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($Winget) {
        winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
    } else {
        Write-Host "[WARN] Please install FFmpeg manually and add it to PATH." -ForegroundColor Yellow
    }
}

# 4. Create .venv & install Studio dependencies
Write-Host "[4/6] Setting up virtual environment (.venv) and installing dependencies..." -ForegroundColor Cyan
if (-not (Test-Path "$RepoDir\.venv")) {
    & python -m venv "$RepoDir\.venv"
}
$VenvPy  = "$RepoDir\.venv\Scripts\python.exe"
$VenvPip = "$RepoDir\.venv\Scripts\pip.exe"
& $VenvPy -m pip install --upgrade pip -q
& $VenvPip install -r "$RepoDir\pipeline\requirements.txt"

# 5. Create .env from template if missing
if (-not (Test-Path "$RepoDir\.env") -and (Test-Path "$RepoDir\.env.example")) {
    Copy-Item "$RepoDir\.env.example" "$RepoDir\.env"
    Write-Host "[5/6] Created .env from .env.example (defaults to 127.0.0.1)" -ForegroundColor Green
} else {
    Write-Host "[5/6] Using existing .env configuration" -ForegroundColor Green
}

# 6. Self-check & Local AI Services Status
Write-Host "[6/6] Verifying Studio installation..." -ForegroundColor Cyan
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
