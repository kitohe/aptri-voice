"""Hold-to-record hotkey: platform-dispatch shim.

Public API: `HotkeyConfig` and `HoldHotkey`. Implementations live in
`_hotkey_win32` (uses `keyboard` / WH_KEYBOARD_LL) and `_hotkey_darwin`
(uses `pynput` global Listener).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class HotkeyConfig:
    # Combo using '+'-separated tokens, e.g. "ctrl+alt+space", "cmd+option+space".
    # Modifier names are normalized across platforms ("win" == "cmd", "option" == "alt").
    combo: str = "ctrl+alt+space"
    # Suppress the combo from the OS. Only effective on Windows; ignored on macOS
    # (pynput cannot selectively swallow a single combo).
    suppress: bool = False


if sys.platform == "win32":
    from ._hotkey_win32 import HoldHotkey  # noqa: F401
elif sys.platform == "darwin":
    from ._hotkey_darwin import HoldHotkey  # noqa: F401
else:
    raise ImportError(
        f"aptri_voice.hotkey: unsupported platform {sys.platform!r} "
        "(currently win32 and darwin only)."
    )


__all__ = ["HoldHotkey", "HotkeyConfig"]
