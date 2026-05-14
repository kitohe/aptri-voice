# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Push-to-talk speech-to-text. Hold a hotkey, speak, release — the transcription is typed into the focused window. Whisper `large-v3-turbo` runs locally via one of three backends (CUDA fp16, Apple Silicon MLX fp16, CPU fp32). Windows and macOS (Apple Silicon) only — Linux has no hotkey/injector implementation.

## Commands

```bash
./setup.sh                  # macOS/Linux: create .venv, install deps, pre-download model
setup.bat                   # Windows equivalent
./run.sh   [args]           # activate .venv and launch (run.bat on Windows)
python -m aptri_voice [args] # direct launch (venv must be active)
python -m aptri_voice --list-devices
```

There is no test suite and no linter configured. Verify changes by running the app.

Supported Python: 3.11–3.14 (`requires-python` in `pyproject.toml`). The version gate is duplicated in `setup.sh` and `setup.bat` — keep all three in sync.

## Architecture

The flow is `hotkey → recorder → transcriber → injector`, wired together in `app.py` (`App` class). Read these together to understand the big picture:

- **`app.py`** — orchestrator. The hotkey press/release callbacks run on the OS hook thread and must never block: `_on_press` only starts the recorder; `_on_release` immediately hands off to a **single-slot `ThreadPoolExecutor`** which does stop → transcribe → inject. Blocking the hook thread >300 ms causes Windows to silently disable the hook.

- **Platform-dispatch shims.** `hotkey.py` and `injector.py` are thin shims that re-export from `_hotkey_{win32,darwin}.py` / `_injector_{win32,darwin}.py` based on `sys.platform`. The public API (`HoldHotkey` + `HotkeyConfig`; `inject()`) is identical across platforms — put platform-specific logic in the `_*` files, not the shims. Modifier names are normalized cross-platform: `win`==`cmd`, `option`==`alt`.

- **`transcribers/`** — backend-agnostic. `base.py` defines the `TranscriberLike` Protocol (just `transcribe(audio, sample_rate) -> str`). `factory.py::build_transcriber` does `auto` selection (MLX on Apple Silicon → CUDA → CPU) and lazy-imports the chosen backend so torch isn't loaded when MLX is used and vice versa. `torch_hf.py` and `mlx.py` are the implementations; each defines its own `DEFAULT_MODEL_ID`.

- **`recorder.py`** — `sounddevice` PortAudio stream, 16 kHz mono float32 (Whisper-native). Returns a result with `too_short`/`duration_s`/`audio`; presses shorter than `MIN_DURATION_S` are dropped by `app.py`.

- **Injection strategy.** Short text is typed key-by-key; text longer than `PASTE_THRESHOLD` chars is sent via clipboard paste, with the original clipboard restored best-effort.

## Platform constraints to keep in mind

- **macOS** needs Accessibility permission for the global listener and injected output to work at all — without it `pynput` runs silently with no events.
- **MLX** requires an arm64-native Python; a Rosetta/x86 interpreter silently has no `mlx-whisper` wheel.
- `--suppress-hotkey` only does anything on Windows; `pynput` can't selectively swallow a combo.
