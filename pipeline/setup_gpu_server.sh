#!/usr/bin/env bash
# =============================================================================
# Ubuntu GPU Server Setup (RTX 5060 Ti 16GB @ 192.168.0.235)
# Installs:
#   1. Static FFmpeg + FFprobe into ~/.local/bin (no sudo required)
#   2. ComfyUI + ComfyUI-GGUF into ~/ComfyUI (reusing Python 3.11 + PyTorch cu130)
#   3. Qwen-Image FP8/INT8 diffusion model + Qwen2.5-VL-7B text encoder + VAE
#   4. faster-whisper into ~/sketch-pipeline-venv
# =============================================================================
set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"
mkdir -p "$HOME/.local/bin"

echo "[1/4] Checking FFmpeg..."
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "Installing static FFmpeg into ~/.local/bin ..."
  TMP_FF=$(mktemp -d)
  curl -L --progress-bar https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz -o "$TMP_FF/ffmpeg.tar.xz"
  tar -xf "$TMP_FF/ffmpeg.tar.xz" -C "$TMP_FF"
  cp "$TMP_FF"/ffmpeg-*-amd64-static/ffmpeg "$HOME/.local/bin/"
  cp "$TMP_FF"/ffmpeg-*-amd64-static/ffprobe "$HOME/.local/bin/"
  chmod +x "$HOME/.local/bin/ffmpeg" "$HOME/.local/bin/ffprobe"
  rm -rf "$TMP_FF"
  echo "FFmpeg installed: $(ffmpeg -version | head -n1)"
else
  echo "FFmpeg already installed: $(ffmpeg -version | head -n1)"
fi

echo "[2/4] Setting up ComfyUI in ~/ComfyUI..."
if [ ! -d "$HOME/ComfyUI" ]; then
  git clone https://github.com/comfyanonymous/ComfyUI.git "$HOME/ComfyUI"
fi

# Create Python 3.11 venv using the same interpreter as Chatterbox (supports PyTorch cu130 on RTX 5060 Ti)
PY311="$(readlink -f "$HOME/Chatterbox/.venv/bin/python")"
if [ ! -d "$HOME/ComfyUI/.venv" ]; then
  "$PY311" -m venv "$HOME/ComfyUI/.venv"
fi
"$HOME/ComfyUI/.venv/bin/pip" install --upgrade pip
"$HOME/ComfyUI/.venv/bin/pip" install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu130
"$HOME/ComfyUI/.venv/bin/pip" install -r "$HOME/ComfyUI/requirements.txt"

# Optional GGUF node support (for INT8/Q8_0/Q4_K_M GGUF weights)
if [ ! -d "$HOME/ComfyUI/custom_nodes/ComfyUI-GGUF" ]; then
  git clone https://github.com/city96/ComfyUI-GGUF.git "$HOME/ComfyUI/custom_nodes/ComfyUI-GGUF"
  "$HOME/ComfyUI/.venv/bin/pip" install -r "$HOME/ComfyUI/custom_nodes/ComfyUI-GGUF/requirements.txt"
fi

echo "[3/4] Downloading Qwen-Image FP8/INT8 models into ~/ComfyUI/models ..."
mkdir -p "$HOME/ComfyUI/models/diffusion_models" \
         "$HOME/ComfyUI/models/text_encoders" \
         "$HOME/ComfyUI/models/vae"

download_if_missing() {
  local url="$1"
  local dest="$2"
  if [ ! -f "$dest" ]; then
    echo "Downloading $(basename "$dest") ..."
    curl -L --progress-bar -C - "$url" -o "$dest"
  else
    echo "Already exists: $dest"
  fi
}

# Comfy-Org official repackaged Qwen-Image FP8 + Qwen2.5-VL-7B FP8 + VAE
download_if_missing \
  "https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/diffusion_models/qwen_image_fp8_e4m3fn.safetensors" \
  "$HOME/ComfyUI/models/diffusion_models/qwen_image_fp8_e4m3fn.safetensors"

download_if_missing \
  "https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors" \
  "$HOME/ComfyUI/models/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors"

download_if_missing \
  "https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/vae/qwen_image_vae.safetensors" \
  "$HOME/ComfyUI/models/vae/qwen_image_vae.safetensors"

cat << 'EOF' > "$HOME/ComfyUI/start_comfyui.sh"
#!/usr/bin/env bash
cd "$HOME/ComfyUI"
exec "$HOME/ComfyUI/.venv/bin/python" main.py --listen 0.0.0.0 --port 8188 --lowvram
EOF
chmod +x "$HOME/ComfyUI/start_comfyui.sh"

echo "[4/4] Installing faster-whisper + pipeline deps into ~/sketch-pipeline-venv ..."
if [ ! -d "$HOME/sketch-pipeline-venv" ]; then
  "$PY311" -m venv "$HOME/sketch-pipeline-venv"
fi
"$HOME/sketch-pipeline-venv/bin/pip" install --upgrade pip
"$HOME/sketch-pipeline-venv/bin/pip" install requests faster-whisper opencv-python-headless numpy Pillow

echo "=== GPU SERVER SETUP COMPLETE ==="
echo "Start ComfyUI with: nohup ~/ComfyUI/start_comfyui.sh > ~/ComfyUI/comfyui.log 2>&1 &"
