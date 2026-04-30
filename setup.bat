@echo off
REM One-shot setup for aptri-voice on Windows.
REM Requires Python 3.12 installed (3.14 is NOT supported - no CUDA wheels yet).

setlocal

where py >nul 2>nul
if errorlevel 1 (
    echo [error] py launcher not found. Install Python 3.12 from python.org.
    exit /b 1
)

py -3.12 --version >nul 2>nul
if errorlevel 1 (
    echo [error] Python 3.12 is required but was not found.
    echo         Install it from https://www.python.org/downloads/release/python-3127/
    echo         then re-run this script.
    exit /b 1
)

if not exist .venv (
    echo [setup] Creating venv with Python 3.12...
    py -3.12 -m venv .venv
)

call .venv\Scripts\activate.bat

echo [setup] Upgrading pip...
python -m pip install --upgrade pip

where nvidia-smi >nul 2>nul
if errorlevel 1 (
    echo [setup] No NVIDIA GPU detected. Installing CPU-only PyTorch...
    pip install torch --index-url https://download.pytorch.org/whl/cpu
) else (
    echo [setup] NVIDIA GPU detected. Installing PyTorch (CUDA 12.4 build)...
    pip install torch --index-url https://download.pytorch.org/whl/cu124
)

echo [setup] Installing remaining dependencies...
pip install -r requirements.txt

echo [setup] Pre-downloading Whisper model (~1.6 GB)...
python -c "from huggingface_hub import snapshot_download; snapshot_download('openai/whisper-large-v3-turbo')"

echo.
echo [done] Setup complete. Activate with:  .venv\Scripts\activate
echo        Then run:                       python -m aptri_voice
echo.

endlocal
