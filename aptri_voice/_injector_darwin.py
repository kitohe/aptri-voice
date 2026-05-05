"""Text injection on macOS via pynput + pyperclip.

Short strings are typed via `pynput.keyboard.Controller.type`. Long strings
go through clipboard + Cmd+V (Terminal.app and iTerm2 both honor Cmd+V, so
we don't need a per-app fallback like the Win32 backend). Original clipboard
contents are restored best-effort; only plain text is preserved.

Requires Accessibility permission for the running interpreter / terminal.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import pyperclip
from pynput.keyboard import Controller, Key

log = logging.getLogger(__name__)

PASTE_THRESHOLD = 200

_kbd = Controller()


def send_unicode(text: str) -> None:
    """Type `text` into the focused window character by character."""
    if not text:
        return
    _kbd.type(text)


def _read_clipboard() -> Optional[str]:
    try:
        return pyperclip.paste()
    except Exception:
        return None


def _write_clipboard(text: str) -> None:
    last: Exception | None = None
    for _ in range(10):
        try:
            pyperclip.copy(text)
            return
        except Exception as e:
            last = e
            time.sleep(0.02)
    raise RuntimeError(f"Failed to write clipboard: {last}")


def _send_cmd_v() -> None:
    with _kbd.pressed(Key.cmd):
        _kbd.press("v")
        _kbd.release("v")


def paste_text(text: str) -> None:
    """Save clipboard, write text, send Cmd+V, restore clipboard."""
    if not text:
        return
    saved = _read_clipboard()
    try:
        _write_clipboard(text)
        time.sleep(0.03)
        _send_cmd_v()
        time.sleep(0.08)
    finally:
        if saved is not None:
            try:
                _write_clipboard(saved)
            except Exception:
                log.debug("clipboard restore failed", exc_info=True)


def inject(text: str, *, prefer_paste_over: int = PASTE_THRESHOLD) -> None:
    """Type `text` into the focused window."""
    if not text or not text.strip():
        return

    if len(text) >= prefer_paste_over:
        try:
            paste_text(text)
            return
        except Exception:
            log.warning("paste_text failed; falling back to typing", exc_info=True)

    send_unicode(text)


__all__ = ["inject", "send_unicode", "paste_text", "PASTE_THRESHOLD"]
