@echo off
REM Activate the project venv and launch aptri-voice.

setlocal

if not exist .venv\Scripts\activate.bat (
    echo [error] .venv not found. Run setup.bat first.
    exit /b 1
)

call .venv\Scripts\activate.bat
python -m aptri_voice %*

endlocal
