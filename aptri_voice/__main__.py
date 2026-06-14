"""Entry point: `python -m aptri_voice`."""
from __future__ import annotations

import argparse
import logging
import sys

from ._single_instance import AlreadyRunning, SingleInstance
from .app import App, run_with_tray
from .recorder import Recorder
from .transcribers import build_transcriber


def _list_devices() -> None:
    for d in Recorder.list_input_devices():
        print(f"  [{d['index']:>2}] {d['name']}  (default {d['default_sr']} Hz)")


_DEFAULT_HOTKEY = "ctrl+opt" if sys.platform == "darwin" else "ctrl+win"


def _use_thread_lock_for_tqdm() -> None:
    """Stop tqdm from creating a multiprocessing lock.

    tqdm (used by mlx-whisper's progress bar and by huggingface_hub downloads)
    defensively builds a multiprocessing RLock for cross-process progress bars.
    That lock is a POSIX semaphore registered with multiprocessing's
    resource_tracker. We're a single process, so the lock is unnecessary; but on
    an abrupt exit (Ctrl+C / tray quit) its finalizer may not run before the
    tracker shuts down, producing "leaked semaphore objects" warnings. Giving
    tqdm a plain threading lock before its first use means the semaphore is never
    created, so there is nothing to leak. Must run before any tqdm instance.
    """
    try:
        import threading

        import tqdm

        tqdm.tqdm.set_lock(threading.RLock())
    except Exception:  # tqdm missing or API change - non-fatal
        pass


def main(argv: list[str] | None = None) -> int:
    _use_thread_lock_for_tqdm()
    parser = argparse.ArgumentParser(prog="aptri-voice")
    parser.add_argument(
        "--hotkey",
        default=_DEFAULT_HOTKEY,
        help=f'Hotkey combo (default: "{_DEFAULT_HOTKEY}"). '
        'Modifiers: ctrl, alt/option, shift, cmd/win. '
        'Examples: "ctrl+alt+space", "cmd+option+space".',
    )
    parser.add_argument(
        "--suppress-hotkey",
        action="store_true",
        help="Swallow the hotkey from the OS (Windows only; ignored on macOS).",
    )
    parser.add_argument(
        "--device",
        default=None,
        help="Input device index or name substring. Use --list-devices to see options.",
    )
    parser.add_argument("--list-devices", action="store_true")
    parser.add_argument(
        "--language",
        default=None,
        help='BCP-47 language code (e.g. "en", "pl"). Default: auto-detect.',
    )
    parser.add_argument(
        "--device-mode",
        choices=("auto", "cuda", "cpu", "mlx"),
        default="auto",
        help="Compute backend (default: auto). 'mlx' is Apple Silicon only.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override model id. Default: openai/whisper-large-v3-turbo "
        "(torch) or mlx-community/whisper-large-v3-turbo (mlx).",
    )
    parser.add_argument("--no-tray", action="store_true", help="Don't show a tray icon.")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.list_devices:
        _list_devices()
        return 0

    # Refuse to start a second instance: two would both grab the hotkey and both
    # type into the focused window, producing interleaved/duplicated output.
    try:
        _guard = SingleInstance()  # noqa: F841  held for the process lifetime
    except AlreadyRunning as e:
        logging.error("%s. Refusing to start a second instance.", e)
        return 1

    device_arg: int | str | None = args.device
    if device_arg is not None:
        try:
            device_arg = int(device_arg)
        except ValueError:
            pass  # leave as substring

    transcriber = build_transcriber(
        device_mode=args.device_mode,
        model_id=args.model,
        language=args.language,
    )
    app = App(
        transcriber=transcriber,
        hotkey_combo=args.hotkey,
        suppress_hotkey=args.suppress_hotkey,
        input_device=device_arg,
    )

    if args.no_tray:
        app.run()
    else:
        try:
            run_with_tray(app)
        except ImportError:
            logging.warning("pystray/Pillow not available; running without tray.")
            app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
