"""Text injection via SendInput (KEYEVENTF_UNICODE) with clipboard-paste fallback."""
from __future__ import annotations

import ctypes
import logging
import time
from ctypes import wintypes

import win32clipboard
import win32con

log = logging.getLogger(__name__)

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_CONTROL = 0x11
VK_V = 0x56

ULONG_PTR = ctypes.c_size_t


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUT_UNION)]


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
_user32.SendInput.restype = wintypes.UINT
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
_user32.GetClassNameW.restype = ctypes.c_int


PASTE_THRESHOLD = 200


# Window class names that don't honor Ctrl+V (terminals, mostly).
_TERMINAL_CLASSES = {
    "CASCADIA_HOSTING_WINDOW_CLASS",  # Windows Terminal
    "ConsoleWindowClass",              # legacy cmd.exe
    "PseudoConsoleWindow",
}


def _foreground_class_name() -> str:
    try:
        hwnd = _user32.GetForegroundWindow()
        if not hwnd:
            return ""
        buf = ctypes.create_unicode_buffer(256)
        _user32.GetClassNameW(hwnd, buf, len(buf))
        return buf.value
    except Exception:
        return ""


def _make_unicode_event(scan: int, key_up: bool) -> INPUT:
    flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if key_up else 0)
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.ki = KEYBDINPUT(wVk=0, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=0)
    return inp


def send_unicode(text: str) -> None:
    """Type `text` into the focused window via SendInput Unicode events."""
    if not text:
        return

    utf16 = text.encode("utf-16-le")
    code_units = [
        int.from_bytes(utf16[i : i + 2], "little") for i in range(0, len(utf16), 2)
    ]

    events = []
    for cu in code_units:
        events.append(_make_unicode_event(cu, key_up=False))
        events.append(_make_unicode_event(cu, key_up=True))

    BATCH = 64
    for i in range(0, len(events), BATCH):
        batch = events[i : i + BATCH]
        arr = (INPUT * len(batch))(*batch)
        sent = _user32.SendInput(len(batch), arr, ctypes.sizeof(INPUT))
        if sent != len(batch):
            err = ctypes.get_last_error()
            raise OSError(err, f"SendInput sent {sent}/{len(batch)} (UIPI?)")


def _read_clipboard_unicode() -> str | None:
    win32clipboard.OpenClipboard()
    try:
        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
            return win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
        return None
    finally:
        win32clipboard.CloseClipboard()


def _write_clipboard_unicode(text: str) -> None:
    last: Exception | None = None
    for _ in range(10):
        try:
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
                return
            finally:
                win32clipboard.CloseClipboard()
        except Exception as e:
            last = e
            time.sleep(0.02)
    raise RuntimeError(f"Failed to write clipboard: {last}")


def _send_ctrl_v() -> None:
    def _vk(vk: int, key_up: bool) -> INPUT:
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        flags = KEYEVENTF_KEYUP if key_up else 0
        inp.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=0)
        return inp

    seq = [
        _vk(VK_CONTROL, False),
        _vk(VK_V, False),
        _vk(VK_V, True),
        _vk(VK_CONTROL, True),
    ]
    arr = (INPUT * len(seq))(*seq)
    _user32.SendInput(len(seq), arr, ctypes.sizeof(INPUT))


def paste_text(text: str) -> None:
    """Save clipboard, write text, send Ctrl+V, restore clipboard."""
    if not text:
        return
    saved = _read_clipboard_unicode()
    try:
        _write_clipboard_unicode(text)
        time.sleep(0.03)
        _send_ctrl_v()
        time.sleep(0.08)
    finally:
        if saved is not None:
            try:
                _write_clipboard_unicode(saved)
            except Exception:
                log.debug("clipboard restore failed", exc_info=True)


def inject(text: str, *, prefer_paste_over: int = PASTE_THRESHOLD) -> None:
    """Type `text` into the focused window.

    Uses SendInput Unicode for short strings; clipboard paste for long ones,
    except in terminals where Ctrl+V isn't honored.
    """
    if not text or not text.strip():
        return

    in_terminal = _foreground_class_name() in _TERMINAL_CLASSES
    if len(text) >= prefer_paste_over and not in_terminal:
        try:
            paste_text(text)
            return
        except Exception:
            log.warning("paste_text failed; falling back to SendInput", exc_info=True)

    send_unicode(text)


__all__ = ["inject", "send_unicode", "paste_text", "PASTE_THRESHOLD"]
