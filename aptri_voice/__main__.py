"""Entry point: `python -m aptri_voice`."""
from __future__ import annotations

import argparse
import logging
import sys

from .app import App, run_with_tray
from .recorder import Recorder
from .transcriber import Transcriber


def _list_devices() -> None:
    for d in Recorder.list_input_devices():
        print(f"  [{d['index']:>2}] {d['name']}  (default {d['default_sr']} Hz)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aptri-voice")
    parser.add_argument(
        "--hotkey",
        default="ctrl+alt+space",
        help='Hotkey combo (default: "ctrl+alt+space"). Examples: "win+space", "right alt+space".',
    )
    parser.add_argument(
        "--suppress-hotkey",
        action="store_true",
        help="Swallow the hotkey from the OS (needed if the combo is taken, e.g. win+space).",
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
        choices=("auto", "cuda", "cpu"),
        default="auto",
        help="Compute device for the model (default: auto).",
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

    device_arg: int | str | None = args.device
    if device_arg is not None:
        try:
            device_arg = int(device_arg)
        except ValueError:
            pass  # leave as substring

    transcriber = Transcriber(device=args.device_mode, language=args.language)
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
