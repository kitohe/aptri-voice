#!/usr/bin/env bash
# One-shot setup for aptri-voice on macOS / Linux.
# On Apple Silicon this installs the [mlx] extra and the mlx-community
# Whisper weights. On Linux it installs the CPU torch path. (CUDA on
# Linux: pick the correct torch index URL by hand.)

set -euo pipefail

if ! command -v python3 >/dev/null 2>&1; then
    echo "[error] python3 not found. Install Python 3.11 or 3.12." >&2
    exit 1
fi

PYBIN="${PYTHON:-python3}"
PYVER=$("$PYBIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
case "$PYVER" in
    3.11|3.12) ;;
    *)
        echo "[error] Python 3.11 or 3.12 required (found $PYVER)." >&2
        echo "        3.13+ is not supported (no torch + mlx wheels for it yet)." >&2
        exit 1
        ;;
esac

OS=$(uname -s)
ARCH=$(uname -m)

if [ ! -d .venv ]; then
    echo "[setup] Creating venv with Python $PYVER..."
    "$PYBIN" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "[setup] Upgrading pip..."
python -m pip install --upgrade pip

if [ "$OS" = "Darwin" ] && [ "$ARCH" = "arm64" ]; then
    echo "[setup] Apple Silicon detected. Installing with [mlx] extra..."
    pip install -e ".[mlx]"
    MODEL_ID="mlx-community/whisper-large-v3-turbo"
else
    echo "[setup] Installing CPU PyTorch..."
    pip install torch --index-url https://download.pytorch.org/whl/cpu
    pip install -e .
    MODEL_ID="openai/whisper-large-v3-turbo"
fi

echo "[setup] Pre-downloading Whisper model ($MODEL_ID, ~1.6 GB)..."
python -c "from huggingface_hub import snapshot_download; snapshot_download('$MODEL_ID')"

echo
echo "[done] Setup complete. Activate with:  source .venv/bin/activate"
echo "       Then run:                       python -m aptri_voice"
echo
