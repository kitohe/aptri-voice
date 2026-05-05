"""Hold-to-record hotkey for macOS via `pynput`.

Requires the user to grant Accessibility permission to the running terminal /
Python interpreter (System Settings → Privacy & Security → Accessibility),
otherwise pynput's global Listener silently receives no events.

Combo syntax (case-insensitive, '+'-separated):
  modifiers : cmd | win | super | ctrl | alt | option | shift
  triggers  : space, enter, tab, esc, f1..f12, or a single character
Pure-modifier combos like "cmd+option" are supported (engage when all required
modifiers are held simultaneously, release when any of them goes up).
"""
from __future__ import annotations

import logging
import threading
from typing import Callable, Optional, Set

from pynput import keyboard as pk

log = logging.getLogger(__name__)


_MODIFIER_ALIASES = {
    "cmd": "cmd",
    "win": "cmd",
    "super": "cmd",
    "ctrl": "ctrl",
    "control": "ctrl",
    "alt": "alt",
    "option": "alt",
    "opt": "alt",
    "shift": "shift",
}

_MODIFIER_KEYS = {
    "cmd": {pk.Key.cmd, pk.Key.cmd_l, pk.Key.cmd_r},
    "ctrl": {pk.Key.ctrl, pk.Key.ctrl_l, pk.Key.ctrl_r},
    "alt": {pk.Key.alt, pk.Key.alt_l, pk.Key.alt_r},
    "shift": {pk.Key.shift, pk.Key.shift_l, pk.Key.shift_r},
}


def _modifier_name(key) -> Optional[str]:
    for name, members in _MODIFIER_KEYS.items():
        if key in members:
            return name
    return None


def _parse_combo(combo: str):
    """Returns (required_modifier_names, trigger_key_or_None)."""
    mods: Set[str] = set()
    trigger = None
    for raw in combo.split("+"):
        part = raw.strip().lower()
        if not part:
            continue
        if part in _MODIFIER_ALIASES:
            mods.add(_MODIFIER_ALIASES[part])
            continue
        if hasattr(pk.Key, part):
            trigger = getattr(pk.Key, part)
            continue
        if len(part) == 1:
            trigger = pk.KeyCode.from_char(part)
            continue
        raise ValueError(f"Unknown key in combo: {part!r}")
    return mods, trigger


def _key_matches(key, trigger) -> bool:
    if trigger is None:
        return False
    if isinstance(trigger, pk.Key):
        return key == trigger
    if isinstance(key, pk.KeyCode) and isinstance(trigger, pk.KeyCode):
        if trigger.vk is not None and getattr(key, "vk", None) is not None:
            return key.vk == trigger.vk
        return getattr(key, "char", None) == getattr(trigger, "char", None)
    return False


class HoldHotkey:
    """Press-and-hold hotkey using a pynput global Listener."""

    def __init__(
        self,
        cfg,
        on_press: Callable[[], None],
        on_release: Callable[[], None],
    ) -> None:
        self._cfg = cfg
        self._on_press = on_press
        self._on_release = on_release
        self._required_mods, self._trigger = _parse_combo(cfg.combo)
        self._held_mods: Set[str] = set()
        self._engaged = False
        self._lock = threading.Lock()
        self._listener: Optional[pk.Listener] = None

        if getattr(cfg, "suppress", False):
            log.warning(
                "--suppress-hotkey is not supported on macOS (pynput cannot "
                "selectively swallow a single combo). Ignoring."
            )

    def start(self) -> None:
        self._listener = pk.Listener(
            on_press=self._handle_press, on_release=self._handle_release
        )
        self._listener.start()
        log.debug(
            "macOS hotkey listener started: mods=%s trigger=%s",
            self._required_mods, self._trigger,
        )

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def _handle_press(self, key) -> None:
        mod = _modifier_name(key)
        if mod is not None:
            self._held_mods.add(mod)
            if self._trigger is None and self._required_mods.issubset(self._held_mods):
                self._engage()
            return

        if _key_matches(key, self._trigger) and self._required_mods.issubset(
            self._held_mods
        ):
            self._engage()

    def _handle_release(self, key) -> None:
        mod = _modifier_name(key)
        if mod is not None:
            self._held_mods.discard(mod)
            # If a required modifier dropped while engaged, release.
            if mod in self._required_mods:
                self._disengage()
            return

        if _key_matches(key, self._trigger):
            self._disengage()

    def _engage(self) -> None:
        with self._lock:
            if self._engaged:
                return
            self._engaged = True
        try:
            self._on_press()
        except Exception:
            with self._lock:
                self._engaged = False
            raise

    def _disengage(self) -> None:
        with self._lock:
            if not self._engaged:
                return
            self._engaged = False
        try:
            self._on_release()
        except Exception:
            log.exception("on_release callback raised")


__all__ = ["HoldHotkey"]
