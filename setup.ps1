<#
.SYNOPSIS
    AI Explainer & Whiteboard Sketch Studio — 1-Click Setup for Windows (PowerShell)

.EXAMPLE
    .\setup.ps1                    # Install Studio (.venv, FFmpeg, .env) & check GPU/services
    .\setup.ps1 -Start             # Setup Studio + launch Web UI on :8090
    .\setup.ps1 -WithAI -Start     # Full install (Ollama + gemma3:12b, ComfyUI + Qwen-Image, Chatterbox) + launch all
#>
param(
    [switch]$WithAI,
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
$TorchIndexUrl = ""
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
        if ($CudaVer -like "13.*") { $TorchIndexUrl = "https://download.pytorch.org/whl/cu130" }
        elseif ($CudaVer -like "12.8*" -or $CudaVer -like "12.9*") { $TorchIndexUrl = "https://download.pytorch.org/whl/cu128" }
        elseif ($CudaVer -like "12.*") { $TorchIndexUrl = "https://download.pytorch.org/whl/cu124" }
    } catch {
        Write-Host "[2/6] [WARN] nvidia-smi failed to query GPU. Update/reinstall your NVIDIA driver." -ForegroundColor Yellow
    }
} else {
    Write-Host "[2/6] [WARN] nvidia-smi not found. Install the latest NVIDIA driver for local AI, or set SKETCH_GPU_HOST in .env to a remote GPU server." -ForegroundColor Yellow
}

# 3. Check FFmpeg
$FfmpegCmd = Get-Command ffmpeg -ErrorAction SilentlyContinue
if ($FfmpegCmd) {
    Write-Host "[3/6] FFmpeg found: $($FfmpegCmd.Source)" -ForegroundColor Green
} else {
    Write-Host "[3/6] FFmpeg not found on PATH. Installing via winget..." -ForegroundColor Yellow
    $Winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($Winget) {
        winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
    } else {
        Write-Host "[WARN] Please install FFmpeg manually and add it to PATH." -ForegroundColor Yellow
    }
}

# 4. Create Studio .venv & install dependencies
Write-Host "[4/6] Setting up virtual environment (.venv) and installing Studio dependencies..." -ForegroundColor Cyan
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

# Optional: Full Local AI Stack (-WithAI)
$ComfyDir      = if ($env:COMFYUI_DIR)    { $env:COMFYUI_DIR }    else { Join-Path $HOME "ComfyUI" }
$ChatterboxDir = if ($env:CHATTERBOX_DIR) { $env:CHATTERBOX_DIR } else { Join-Path $HOME "Chatterbox" }

if ($WithAI) {
    Write-Host ""
    Write-Host "[AI 1/3] Setting up Ollama + gemma3:12b ..." -ForegroundColor Cyan
    if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            winget install --id Ollama.Ollama -e --accept-source-agreements --accept-package-agreements
        } else {
            Write-Host "[WARN] Install Ollama from https://ollama.com/download then run: ollama pull gemma3:12b" -ForegroundColor Yellow
        }
    }
    if (Get-Command ollama -ErrorAction SilentlyContinue) {
        & ollama pull gemma3:12b
    }

    Write-Host "[AI 2/3] Setting up ComfyUI + Qwen-Image models in $ComfyDir ..." -ForegroundColor Cyan
    if (-not (Test-Path $ComfyDir)) {
        & git clone https://github.com/comfyanonymous/ComfyUI.git $ComfyDir
    }
    if (-not (Test-Path "$ComfyDir\.venv")) {
        & python -m venv "$ComfyDir\.venv"
        & "$ComfyDir\.venv\Scripts\python.exe" -m pip install --upgrade pip -q
        if ($TorchIndexUrl) {
            & "$ComfyDir\.venv\Scripts\pip.exe" install torch torchvision torchaudio --index-url $TorchIndexUrl
        } else {
            & "$ComfyDir\.venv\Scripts\pip.exe" install torch torchvision torchaudio
        }
        & "$ComfyDir\.venv\Scripts\pip.exe" install -r "$ComfyDir\requirements.txt"
    }

    $ModelDirs = @("diffusion_models", "text_encoders", "vae", "loras")
    foreach ($d in $ModelDirs) { New-Item -ItemType Directory -Force -Path (Join-Path $ComfyDir "models\$d") | Out-Null }

    function Get-ModelIfMissing($Url, $Dest) {
        if (-not (Test-Path $Dest)) {
            Write-Host "         Downloading $(Split-Path -Leaf $Dest)..." -ForegroundColor Cyan
            & curl.exe -L -C - --progress-bar $Url -o $Dest
        } else {
            Write-Host "         Already exists: $(Split-Path -Leaf $Dest)" -ForegroundColor Green
        }
    }

    Get-ModelIfMissing "https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/diffusion_models/qwen_image_fp8_e4m3fn.safetensors" (Join-Path $ComfyDir "models\diffusion_models\qwen_image_fp8_e4m3fn.safetensors")
    Get-ModelIfMissing "https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors" (Join-Path $ComfyDir "models\text_encoders\qwen_2.5_vl_7b_fp8_scaled.safetensors")
    Get-ModelIfMissing "https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/vae/qwen_image_vae.safetensors" (Join-Path $ComfyDir "models\vae\qwen_image_vae.safetensors")
    Get-ModelIfMissing "https://huggingface.co/lightx2v/Qwen-Image-Lightning/resolve/main/Qwen-Image-Lightning-8steps-V2.0-bf16.safetensors" (Join-Path $ComfyDir "models\loras\Qwen-Image-Lightning-8steps-V2.0-bf16.safetensors")

    Write-Host "[AI 3/3] Setting up Chatterbox TTS Server in $ChatterboxDir ..." -ForegroundColor Cyan
    if (-not (Test-Path $ChatterboxDir)) {
        & git clone https://github.com/devnen/Chatterbox-TTS-Server.git $ChatterboxDir
    }
    if (-not (Test-Path "$ChatterboxDir\.venv")) {
        & python -m venv "$ChatterboxDir\.venv"
        & "$ChatterboxDir\.venv\Scripts\python.exe" -m pip install --upgrade pip -q
        if ($TorchIndexUrl) {
            & "$ChatterboxDir\.venv\Scripts\pip.exe" install torch torchvision torchaudio --index-url $TorchIndexUrl
        } else {
            & "$ChatterboxDir\.venv\Scripts\pip.exe" install torch torchvision torchaudio
        }
        if (Test-Path "$ChatterboxDir\requirements.txt") {
            & "$ChatterboxDir\.venv\Scripts\pip.exe" install -r "$ChatterboxDir\requirements.txt"
        }
    }

    if ($Start) {
        Write-Host "         Launching ComfyUI (:8188) and Chatterbox (:8004) in background windows..." -ForegroundColor Green
        Start-Process -FilePath "$ComfyDir\.venv\Scripts\python.exe" -ArgumentList "main.py --listen 0.0.0.0 --port 8188 --lowvram" -WorkingDirectory $ComfyDir
        Start-Process -FilePath "$ChatterboxDir\.venv\Scripts\python.exe" -ArgumentList "server.py" -WorkingDirectory $ChatterboxDir
        Start-Sleep -Seconds 4
    }
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
