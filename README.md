<p align="center">
  <img src="assets/logo.png" alt="aptri-voice logo" width="220">
</p>

# aptri-voice

Push-to-talk speech-to-text for Windows. Hold a hotkey, speak, release — text is typed into whatever window is focused. Uses [`openai/whisper-large-v3-turbo`](https://huggingface.co/openai/whisper-large-v3-turbo) loaded directly via Hugging Face `transformers`, with CUDA fp16 acceleration on NVIDIA GPUs and a CPU fp32 fallback.

## Requirements

- Windows 10/11
- **Python 3.12** (3.11 also works). **3.13 and 3.14 are not yet supported** — there are no CUDA wheels for them on the PyTorch / CTranslate2 indexes as of writing.
- Optional but recommended: NVIDIA GPU with ≥6 GB VRAM. RTX 3070 Ti / 8 GB is plenty (the transformers fp16 path uses ~3.5–5 GB at runtime). **CPU-only also works** — transcription is just slower (a 5 s clip takes a few seconds on a modern desktop CPU instead of being near-instant on a GPU).
- A working microphone.

## Setup

```bat
setup.bat
```

This creates `.venv` with Python 3.12, auto-detects whether you have an NVIDIA GPU (via `nvidia-smi`) and installs the matching PyTorch build (CUDA 12.4 if a GPU is present, CPU-only otherwise), then installs all other dependencies and pre-downloads the Whisper model (~1.6 GB into `%USERPROFILE%\.cache\huggingface`).

If you'd rather do it by hand:

```bat
py -3.12 -m venv .venv
.venv\Scripts\activate

REM Pick ONE torch install line:
pip install torch --index-url https://download.pytorch.org/whl/cu124   :: NVIDIA GPU
pip install torch --index-url https://download.pytorch.org/whl/cpu     :: CPU-only

pip install -r requirements.txt
huggingface-cli download openai/whisper-large-v3-turbo
```

## Run

```bat
.venv\Scripts\activate
python -m aptri_voice
```

Default hotkey is **`Ctrl+Alt+Space`** (hold to record, release to transcribe). A small red tray icon appears; right-click it to quit.

### Why not `Win+Space`?

`Win+Space` is hardcoded by Windows as the input language switcher. You *can* use it with `--hotkey "win+space" --suppress-hotkey`, but the LWIN modifier still leaks Start-menu chord state into the foreground app in some cases, so `Ctrl+Alt+Space` is the conflict-free default. If you really want `Win+Space`:

```bat
python -m aptri_voice --hotkey "win+space" --suppress-hotkey
```

### Useful flags

```
--hotkey "ctrl+alt+space"   # any keyboard-lib combo
--suppress-hotkey           # swallow it from the OS (needed for win+space)
--language en               # skip auto-detect (faster, more reliable on short clips)
--device-mode auto|cuda|cpu # default auto: cuda if available, else cpu
--device 1                  # mic device index or name substring
--list-devices              # print available input devices
--no-tray                   # run without a tray icon
--log-level DEBUG
```

## How it works

| Layer | Module | Notes |
|---|---|---|
| Hotkey | `aptri_voice/hotkey.py` | WH_KEYBOARD_LL hook via `keyboard` lib; press-and-hold semantics with auto-repeat debounce. |
| Audio capture | `aptri_voice/recorder.py` | `sounddevice` PortAudio stream at 16 kHz mono float32 (Whisper-native). 300 s safety cap. Resamples if device doesn't support 16 kHz. |
| Transcription | `aptri_voice/transcriber.py` | HF `transformers` loading `openai/whisper-large-v3-turbo` directly. fp16 on GPU (sdpa attention), fp32 on CPU. Greedy decoding, no prev-token conditioning. Clips >30 s switch to sequential long-form decoding (`truncation=False`, `padding="longest"`, `return_attention_mask=True`, `return_timestamps=True`) so the feature extractor doesn't crop to a single 30 s window. |
| Text injection | `aptri_voice/injector.py` | Win32 `SendInput` with `KEYEVENTF_UNICODE` for short text; clipboard-paste fallback (`Ctrl+V`) for long text, with original clipboard contents restored. Detects terminals (which use `Ctrl+Shift+V`) and falls through to SendInput. |
| Orchestrator | `aptri_voice/app.py` | Hook callback only sets state and submits to a single-slot worker — never blocks (>300 ms blocks Windows silently disables the hook). |

## Pitfalls

- **Python version**: must be 3.12 or 3.11 right now.
- **Elevated windows**: a non-elevated process cannot inject input into elevated apps (Task Manager, admin Terminal). Run elevated only if you accept that tradeoff.
- **Antivirus / SmartScreen**: low-level keyboard hook + `SendInput` is the textbook keylogger fingerprint. Some AVs flag `keyboard` and PyInstaller bundles. Add an exclusion if needed.
- **Clipboard restore is best-effort**: only `CF_UNICODETEXT` is preserved. Images/files/RTF on the clipboard at the time of a long-text injection are lost.
- **First run is slow**: model downloads (~1.6 GB) and CUDA kernels JIT on first transcription. The transcriber's `__init__` does a 1-second warmup so the first real press is fast.
