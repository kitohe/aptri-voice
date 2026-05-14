#!/usr/bin/env bash
# Activate the project venv and launch aptri-voice.

set -euo pipefail

if [ ! -f .venv/bin/activate ]; then
    echo "[error] .venv not found. Run ./setup.sh first." >&2
    exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate
exec python -m aptri_voice "$@"
