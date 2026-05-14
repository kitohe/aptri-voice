@echo off
REM One-shot setup for aptri-voice on Windows.
REM Requires Python 3.11-3.14 installed.

setlocal

where py >nul 2>nul
if errorlevel 1 (
    echo [error] py launcher not found. Install Python 3.11-3.14 from python.org.
    exit /b 1
)

set PYTAG=
for %%V in (3.14 3.13 3.12 3.11) do (
    if not defined PYTAG (
        py -%%V --version >nul 2>nul
        if not errorlevel 1 set PYTAG=%%V
    )
)

if not defined PYTAG (
    echo [error] Python 3.11-3.14 is required but was not found.
    echo         Install it from https://www.python.org/downloads/
    echo         then re-run this script.
    exit /b 1
)

if not exist .venv (
    echo [setup] Creating venv with Python %PYTAG%...
    py -%PYTAG% -m venv .venv
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
