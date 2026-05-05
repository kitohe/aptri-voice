"""Wires hotkey -> recorder -> transcriber -> injector."""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from .hotkey import HoldHotkey, HotkeyConfig
from .injector import inject
from .recorder import Recorder
from .transcribers import TranscriberLike

log = logging.getLogger("aptri_voice")


class App:
    def __init__(
        self,
        transcriber: TranscriberLike,
        hotkey_combo: str = "ctrl+alt+space",
        suppress_hotkey: bool = False,
        input_device: int | str | None = None,
    ) -> None:
        self._transcriber = transcriber
        self._recorder = Recorder(device=input_device)
        self._hotkey = HoldHotkey(
            HotkeyConfig(combo=hotkey_combo, suppress=suppress_hotkey),
            on_press=self._on_press,
            on_release=self._on_release,
        )
        # Single-slot worker so back-to-back presses don't interleave injections.
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="stt-worker")
        self._stop_event = threading.Event()

    def _on_press(self) -> None:
        try:
            self._recorder.start()
            log.info("recording started")
        except Exception:
            log.exception("failed to start recorder")

    def _on_release(self) -> None:
        # Hand off so we never block the keyboard hook thread (>300 ms = OS
        # silently disables the hook).
        self._worker.submit(self._finalize)

    def _finalize(self) -> None:
        try:
            result = self._recorder.stop()
        except Exception:
            log.exception("recorder.stop failed")
            return
        if result.too_short:
            log.info("press too short (%.0f ms) - ignored", result.duration_s * 1000)
            return
        log.info("transcribing %.2fs of audio...", result.duration_s)
        try:
            text = self._transcriber.transcribe(result.audio)
        except Exception:
            log.exception("transcription failed")
            return
        if not text or not text.strip():
            log.info("empty transcription - nothing to inject")
            return
        try:
            inject(text)
            log.info("injected %d chars: %s", len(text), text[:80])
        except Exception:
            log.exception("injection failed")

    def run(self) -> None:
        self._hotkey.start()
        log.info("aptri-voice running. Hold the hotkey to dictate. Ctrl+C to quit.")
        try:
            self._stop_event.wait()
        except KeyboardInterrupt:
            pass
        finally:
            self._hotkey.stop()
            self._worker.shutdown(wait=True, cancel_futures=False)

    def stop(self) -> None:
        self._stop_event.set()


def run_with_tray(app: App) -> None:
    """Run with a pystray tray icon for clean quit."""
    import pystray
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (64, 64), "black")
    d = ImageDraw.Draw(img)
    d.ellipse((16, 16, 48, 48), fill="red")

    def on_quit(icon, _item):
        app.stop()
        icon.stop()

    menu = pystray.Menu(pystray.MenuItem("Quit", on_quit))
    icon = pystray.Icon("aptri-voice", img, "Aptri Voice", menu)

    t = threading.Thread(target=app.run, name="aptri-app", daemon=True)
    t.start()
    icon.run()
    t.join()


__all__ = ["App", "run_with_tray"]
