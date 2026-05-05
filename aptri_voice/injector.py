"""Text injector: platform-dispatch shim.

Public API: `inject(text)`. Implementations live in `_injector_win32`
(SendInput + Win32 clipboard) and `_injector_darwin` (pynput + pyperclip).
"""
from __future__ import annotations

import sys

if sys.platform == "win32":
    from ._injector_win32 import inject, paste_text, send_unicode, PASTE_THRESHOLD  # noqa: F401
elif sys.platform == "darwin":
    from ._injector_darwin import inject, paste_text, send_unicode, PASTE_THRESHOLD  # noqa: F401
else:
    raise ImportError(
        f"aptri_voice.injector: unsupported platform {sys.platform!r} "
        "(currently win32 and darwin only)."
    )


__all__ = ["inject", "send_unicode", "paste_text", "PASTE_THRESHOLD"]
