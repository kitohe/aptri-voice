<p align="center">
  <img src="assets/logo.png" alt="aptri-voice logo" width="220">
</p>

# aptri-voice

Push-to-talk speech-to-text. Hold a hotkey, speak, release — text is typed into whatever window is focused. Uses [`whisper-large-v3-turbo`](https://huggingface.co/openai/whisper-large-v3-turbo) with three backends:

- **CUDA fp16** via Hugging Face `transformers` (NVIDIA GPU)
- **MLX fp16** via [`mlx-whisper`](https://github.com/ml-explore/mlx-examples/tree/main/whisper) (Apple Silicon)
- **CPU fp32** via `transformers` (universal fallback)

Hotkey + injection are platform-dispatched: Win32 LL hook + `SendInput` on Windows, `pynput` global Listener + clipboard paste on macOS. Tray icon is `pystray` on both.

## Requirements

- Windows 10/11 **or** macOS 14+ on Apple Silicon (arm64). Linux is not currently supported for the hotkey/injector layer.
- **Python 3.11 or 3.12.** 3.13/3.14 are not yet supported (no CUDA / MLX wheels).
- Optional NVIDIA GPU with ≥6 GB VRAM (the transformers fp16 path uses ~3.5–5 GB at runtime). On Apple Silicon the MLX path uses ~2 GB unified memory and runs at 5–10× CPU PyTorch speed.
- A working microphone.

## Setup

### Windows

```bat
setup.bat
```

Creates `.venv` with Python 3.12, auto-detects an NVIDIA GPU (via `nvidia-smi`) and installs the matching PyTorch build (CUDA 12.4 / CPU), installs the rest, and pre-downloads `openai/whisper-large-v3-turbo` (~1.6 GB).

### macOS (Apple Silicon)

```bash
./setup.sh
```

Detects arm64, installs the `[mlx]` extra (`mlx-whisper`), and pre-downloads `mlx-community/whisper-large-v3-turbo`. Requires macOS 14 (Sonoma) and an arm64-native Python (Rosetta Python silently has no MLX wheel).

**Grant Accessibility permission** the first time you run aptri-voice — pynput's global keyboard listener is silent without it. macOS will prompt; alternatively go to System Settings → Privacy & Security → Accessibility and add your terminal (Terminal.app, iTerm2, VS Code, etc.) or the Python interpreter inside `.venv/bin/`.

### Manual

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate

# Pick the right torch line for your platform:
pip install torch --index-url https://download.pytorch.org/whl/cu124   # NVIDIA GPU
pip install torch --index-url https://download.pytorch.org/whl/cpu     # CPU-only

# On Apple Silicon also:
pip install -e ".[mlx]"

# Otherwise:
pip install -e .

huggingface-cli download openai/whisper-large-v3-turbo            # torch backends
huggingface-cli download mlx-community/whisper-large-v3-turbo     # MLX backend
```

## Run

```bat
.venv\Scripts\activate          :: Windows
source .venv/bin/activate       # macOS
python -m aptri_voice
```

Default hotkey: **`Ctrl+Win`** on Windows, **`Cmd+Option+Space`** on macOS (hold to record, release to transcribe). A small red tray icon appears; right-click it to quit.

Modifier names are platform-flexible: `cmd` and `win` are aliases (mapped to the OS meta key), and `option` is an alias for `alt`. So `--hotkey "ctrl+alt+space"` works identically on both platforms.

### Why not `Win+Space`?

`Win+Space` is hardcoded by Windows as the input language switcher. You *can* use it with `--hotkey "win+space" --suppress-hotkey`, but the LWIN modifier still leaks Start-menu chord state into the foreground app in some cases, so `Ctrl+Alt+Space` is the conflict-free default. If you really want `Win+Space`:

```bat
python -m aptri_voice --hotkey "win+space" --suppress-hotkey
```

### Useful flags

```
--hotkey "ctrl+alt+space"       # combo: ctrl|alt|option|shift|cmd|win + key
--suppress-hotkey               # swallow it from the OS (Windows only; ignored on macOS)
--language en                   # skip auto-detect (faster, more reliable on short clips)
--device-mode auto|cuda|cpu|mlx # default auto: mlx (Apple Silicon) > cuda > cpu
--model REPO_ID                 # override the default Whisper model id
--device 1                      # mic device index or name substring
--list-devices                  # print available input devices
--no-tray                       # run without a tray icon
--log-level DEBUG
```

## How it works

| Layer | Module | Notes |
|---|---|---|
| Hotkey | `aptri_voice/hotkey.py` (+ `_hotkey_win32.py`, `_hotkey_darwin.py`) | Platform-dispatch shim. Windows: WH_KEYBOARD_LL hook via `keyboard` lib. macOS: `pynput` global Listener with manual modifier-state tracking. Both expose `HoldHotkey` with press/release callbacks. |
| Audio capture | `aptri_voice/recorder.py` | `sounddevice` PortAudio stream at 16 kHz mono float32 (Whisper-native). 300 s safety cap. Resamples if device doesn't support 16 kHz. |
| Transcription | `aptri_voice/transcribers/` | Backend-agnostic Protocol with three implementations. `torch_hf.py` uses HF `transformers` with `openai/whisper-large-v3-turbo` (fp16 CUDA / fp32 CPU, sdpa attention, greedy, long-form via `truncation=False` + `return_timestamps=True`). `mlx.py` wraps `mlx_whisper.transcribe` against `mlx-community/whisper-large-v3-turbo` (fp16, numpy buffer in directly, long-form handled internally). `factory.py` does auto-selection: MLX on Apple Silicon, then CUDA, then CPU. |
| Text injection | `aptri_voice/injector.py` (+ `_injector_win32.py`, `_injector_darwin.py`) | Platform-dispatch shim. Windows: `SendInput` with `KEYEVENTF_UNICODE` for short text, clipboard `Ctrl+V` for long text, terminal-class detection to fall through. macOS: `pynput.Controller.type` for short, `pyperclip` + `Cmd+V` for long. Original clipboard restored best-effort on both. |
| Orchestrator | `aptri_voice/app.py` | Hook callback only sets state and submits to a single-slot worker — never blocks (>300 ms blocks Windows silently disables the hook). |

## Pitfalls

- **Python version**: must be 3.12 or 3.11 right now.
- **MLX on macOS**: requires macOS 14+ on Apple Silicon and a native arm64 Python interpreter. A Rosetta/x86 Python will silently fail to find an `mlx-whisper` wheel. Verify with `python -c "import platform; print(platform.machine())"` → `arm64`.
- **macOS Accessibility permission**: required for the global hotkey listener and for typed/pasted output to reach other apps. Without it, `pynput.Listener` runs silently with no events. macOS prompts on first launch; if you missed the prompt, add your terminal (or the venv's Python binary) under System Settings → Privacy & Security → Accessibility.
- **macOS Secure Input**: when a password field is focused (login screens, 1Password, sudo in Terminal), macOS engages Secure Input and blocks all simulated keystrokes — pynput typing and Cmd+V will both no-op. Not fixable from userland.
- **Elevated windows**: a non-elevated process cannot inject input into elevated apps (Task Manager, admin Terminal). Run elevated only if you accept that tradeoff.
- **Antivirus / SmartScreen**: low-level keyboard hook + `SendInput` is the textbook keylogger fingerprint. Some AVs flag `keyboard` and PyInstaller bundles. Add an exclusion if needed.
- **Clipboard restore is best-effort**: only `CF_UNICODETEXT` is preserved. Images/files/RTF on the clipboard at the time of a long-text injection are lost.
- **First run is slow**: model downloads (~1.6 GB) and CUDA kernels JIT on first transcription. The transcriber's `__init__` does a 1-second warmup so the first real press is fast.
