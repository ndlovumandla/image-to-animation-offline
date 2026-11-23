#!/usr/bin/env bash
# =============================================================================
# AI Explainer & Whiteboard Sketch Studio — 1-Click Setup (Linux / macOS)
#
# Usage:
#   ./setup.sh                # Setup Python .venv, FFmpeg check, .env & self-test
#   ./setup.sh --start        # Setup + immediately launch Web Studio on :8090
#   ./setup.sh --with-ai      # Also pull Ollama gemma3:12b & install ComfyUI + Qwen-Image
#   ./setup.sh --with-ai --start
# =============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

WITH_AI=false
AUTO_START=false
PORT="${SKETCH_PORT:-8090}"

for arg in "$@"; do
  case "$arg" in
    --with-ai) WITH_AI=true ;;
    --start)   AUTO_START=true ;;
    -h|--help)
      sed -n '2,10p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg (use --with-ai, --start, or --help)"
      exit 1
      ;;
  esac
done

export PATH="$HOME/.local/bin:$PATH"
mkdir -p "$HOME/.local/bin"

echo "======================================================================"
echo "  AI Explainer & Whiteboard Sketch Studio — 1-Click Setup"
echo "======================================================================"

# 1. Pick Python 3.11 or 3.12
PYTHON_BIN=""
for cand in python3.12 python3.11 python3; do
  if command -v "$cand" >/dev/null 2>&1; then
    VER="$("$cand" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    if [[ "$VER" == "3.11" || "$VER" == "3.12" || "$VER" == "3.13" ]]; then
      PYTHON_BIN="$(command -v "$cand")"
      break
    fi
  fi
done

if [[ -z "$PYTHON_BIN" ]]; then
  echo "[ERROR] Python 3.11+ is required but was not found."
  echo "  Ubuntu/Debian: sudo apt update && sudo apt install -y python3.12 python3.12-venv python3-pip"
  echo "  macOS:         brew install python@3.12"
  exit 1
fi
echo "[1/6] Using Python: $PYTHON_BIN ($("$PYTHON_BIN" --version))"

# 2. Check NVIDIA GPU, Driver & CUDA (nvidia-smi)
TORCH_INDEX_URL=""
if command -v nvidia-smi >/dev/null 2>&1 && GPU_INFO="$(nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader 2>/dev/null | head -n 1)" && [[ -n "$GPU_INFO" ]]; then
  CUDA_VER="$(nvidia-smi 2>/dev/null | sed -n 's/.*CUDA Version: \([0-9][0-9.]*\).*/\1/p' | head -n 1 || true)"
  VRAM_MIB="$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -n 1 | tr -d ' ' || echo 0)"
  echo "[2/6] NVIDIA GPU detected: $GPU_INFO (CUDA ${CUDA_VER:-unknown})"
  if [[ "$VRAM_MIB" =~ ^[0-9]+$ && "$VRAM_MIB" -lt 12000 ]]; then
    echo "      [WARN] Detected ${VRAM_MIB} MiB VRAM; 12–16 GB VRAM is recommended for local Qwen-Image + gemma3:12b."
  fi
  if [[ "${CUDA_VER:-}" == 13.* ]]; then
    TORCH_INDEX_URL="https://download.pytorch.org/whl/cu130"
  elif [[ "${CUDA_VER:-}" == 12.8* || "${CUDA_VER:-}" == 12.9* ]]; then
    TORCH_INDEX_URL="https://download.pytorch.org/whl/cu128"
  elif [[ "${CUDA_VER:-}" == 12.* ]]; then
    TORCH_INDEX_URL="https://download.pytorch.org/whl/cu124"
  fi
  if command -v nvcc >/dev/null 2>&1; then
    echo "      CUDA Toolkit (nvcc): $(nvcc --version | tail -n 1)"
  else
    echo "      [INFO] nvcc toolkit not on PATH (optional — NVIDIA driver + nvidia-smi is sufficient for prebuilt PyTorch/Ollama/ComfyUI)."
  fi
else
  echo "[2/6] [WARN] nvidia-smi not found or NVIDIA GPU driver not active."
  echo "      - To run local AI on an NVIDIA GPU (Ubuntu): sudo ubuntu-drivers install && sudo reboot"
  echo "      - Or set SKETCH_GPU_HOST=<your-gpu-server-ip> in .env to use a remote GPU server."
fi

# 3. Check / install FFmpeg
if command -v ffmpeg >/dev/null 2>&1 && command -v ffprobe >/dev/null 2>&1; then
  echo "[3/6] FFmpeg found: $(ffmpeg -version | head -n 1)"
elif [[ "$(uname -s)" == "Linux" && "$(uname -m)" == "x86_64" ]]; then
  echo "[3/6] FFmpeg not found — installing static FFmpeg into ~/.local/bin (no sudo required)..."
  TMP_FF="$(mktemp -d)"
  curl -L --progress-bar https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz -o "$TMP_FF/ffmpeg.tar.xz"
  tar -xf "$TMP_FF/ffmpeg.tar.xz" -C "$TMP_FF"
  cp "$TMP_FF"/ffmpeg-*-amd64-static/ffmpeg "$HOME/.local/bin/"
  cp "$TMP_FF"/ffmpeg-*-amd64-static/ffprobe "$HOME/.local/bin/"
  chmod +x "$HOME/.local/bin/ffmpeg" "$HOME/.local/bin/ffprobe"
  rm -rf "$TMP_FF"
  echo "      Installed: $(ffmpeg -version | head -n 1)"
else
  echo "[3/6] [WARN] FFmpeg/FFprobe not found on PATH. Please install FFmpeg:"
  echo "      macOS: brew install ffmpeg | Ubuntu: sudo apt install -y ffmpeg"
fi

# 4. Create .venv & install Studio dependencies
echo "[4/6] Setting up virtual environment (.venv) and installing dependencies..."
if [[ ! -d "$REPO_DIR/.venv" ]]; then
  "$PYTHON_BIN" -m venv "$REPO_DIR/.venv"
fi
"$REPO_DIR/.venv/bin/python" -m pip install --upgrade pip -q
"$REPO_DIR/.venv/bin/pip" install -r "$REPO_DIR/pipeline/requirements.txt"

# 5. Create .env from template if missing
if [[ ! -f "$REPO_DIR/.env" && -f "$REPO_DIR/.env.example" ]]; then
  cp "$REPO_DIR/.env.example" "$REPO_DIR/.env"
  echo "[5/6] Created .env from .env.example (defaults to 127.0.0.1)"
else
  echo "[5/6] Using existing .env configuration"
fi

# Optional: Install Local AI Stack (--with-ai)
if [[ "$WITH_AI" == "true" ]]; then
  echo ""
  echo "[AI] Setting up Local AI Services (Ollama gemma3:12b + ComfyUI Qwen-Image)..."
  if command -v ollama >/dev/null 2>&1; then
    echo "     Pulling Ollama gemma3:12b..."
    ollama pull gemma3:12b || echo "[WARN] Could not pull gemma3:12b (is 'ollama serve' running?)"
  else
    echo "[WARN] Ollama not installed. Install with: curl -fsSL https://ollama.com/install.sh | sh"
  fi

  COMFY_DIR="${COMFYUI_DIR:-$HOME/ComfyUI}"
  if [[ ! -d "$COMFY_DIR" ]]; then
    echo "     Cloning ComfyUI into $COMFY_DIR..."
    git clone https://github.com/comfyanonymous/ComfyUI.git "$COMFY_DIR"
  fi
  if [[ ! -d "$COMFY_DIR/.venv" ]]; then
    "$PYTHON_BIN" -m venv "$COMFY_DIR/.venv"
    "$COMFY_DIR/.venv/bin/pip" install --upgrade pip
    if [[ -n "$TORCH_INDEX_URL" ]]; then
      echo "     Installing PyTorch CUDA wheels from $TORCH_INDEX_URL ..."
      "$COMFY_DIR/.venv/bin/pip" install torch torchvision torchaudio --index-url "$TORCH_INDEX_URL"
    else
      "$COMFY_DIR/.venv/bin/pip" install torch torchvision torchaudio
    fi
    "$COMFY_DIR/.venv/bin/pip" install -r "$COMFY_DIR/requirements.txt"
  fi

  mkdir -p "$COMFY_DIR/models/diffusion_models" \
           "$COMFY_DIR/models/text_encoders" \
           "$COMFY_DIR/models/vae" \
           "$COMFY_DIR/models/loras"

  download_if_missing() {
    local url="$1"
    local dest="$2"
    if [[ ! -f "$dest" ]]; then
      echo "     Downloading $(basename "$dest")..."
      curl -L --progress-bar -C - "$url" -o "$dest"
    else
      echo "     Already exists: $(basename "$dest")"
    fi
  }

  download_if_missing \
    "https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/diffusion_models/qwen_image_fp8_e4m3fn.safetensors" \
    "$COMFY_DIR/models/diffusion_models/qwen_image_fp8_e4m3fn.safetensors"
  download_if_missing \
    "https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors" \
    "$COMFY_DIR/models/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors"
  download_if_missing \
    "https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/vae/qwen_image_vae.safetensors" \
    "$COMFY_DIR/models/vae/qwen_image_vae.safetensors"
  download_if_missing \
    "https://huggingface.co/lightx2v/Qwen-Image-Lightning/resolve/main/Qwen-Image-Lightning-8steps-V2.0-bf16.safetensors" \
    "$COMFY_DIR/models/loras/Qwen-Image-Lightning-8steps-V2.0-bf16.safetensors"
fi

# 6. Self-check & Service Status
echo "[6/6] Verifying Studio installation..."
"$REPO_DIR/.venv/bin/python" -c "from pipeline.web_ui import app; from pipeline.config import PipelineConfig; print('      Studio import OK! Default GPU host:', PipelineConfig().gpu_host)"

GPU_HOST="${SKETCH_GPU_HOST:-127.0.0.1}"
check_url() {
  local label="$1"
  local url="$2"
  if curl -fsS --max-time 2 "$url" >/dev/null 2>&1; then
    echo "      [ONLINE]  $label ($url)"
  else
    echo "      [OFFLINE] $label ($url)"
  fi
}

echo ""
echo "Local AI Services Check (host: $GPU_HOST):"
check_url "Ollama (Director & Vision QA)" "http://${GPU_HOST}:11434/api/tags"
check_url "ComfyUI (Qwen-Image)"          "http://${GPU_HOST}:8188/system_stats"
check_url "Chatterbox TTS (Voiceover)"    "http://${GPU_HOST}:8004/health"

echo ""
echo "======================================================================"
echo "  Setup Complete!"
echo "  Start the Web Studio anytime with:"
echo "    source .venv/bin/activate && uvicorn pipeline.web_ui:app --host 0.0.0.0 --port ${PORT}"
echo "  Then open: http://localhost:${PORT}"
echo "======================================================================"

if [[ "$AUTO_START" == "true" ]]; then
  echo "Launching Web Studio UI on http://localhost:${PORT} ..."
  exec "$REPO_DIR/.venv/bin/uvicorn" pipeline.web_ui:app --host 0.0.0.0 --port "$PORT"
fi
