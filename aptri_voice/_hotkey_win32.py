"""Hold-to-record hotkey via the `keyboard` library (WH_KEYBOARD_LL hook)."""
from __future__ import annotations

import threading
from typing import Callable, Iterable

import keyboard


class HoldHotkey:
    """Fires `on_press` on the down-edge and `on_release` on the up-edge."""

    def __init__(
        self,
        cfg,
        on_press: Callable[[], None],
        on_release: Callable[[], None],
    ) -> None:
        self._cfg = cfg
        self._on_press = on_press
        self._on_release = on_release
        self._engaged = False
        self._lock = threading.Lock()

    def start(self) -> None:
        keyboard.add_hotkey(
            self._cfg.combo,
            self._handle_press,
            suppress=self._cfg.suppress,
            trigger_on_release=False,
        )
        for key in self._combo_keys(self._cfg.combo):
            keyboard.on_release_key(key, self._handle_release)

    def stop(self) -> None:
        keyboard.unhook_all_hotkeys()
        keyboard.unhook_all()

    @staticmethod
    def _combo_keys(combo: str) -> Iterable[str]:
        return [part.strip() for part in combo.split("+") if part.strip()]

    def _handle_press(self) -> None:
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

    def _handle_release(self, _event) -> None:
        with self._lock:
            if not self._engaged:
                return
            self._engaged = False
        self._on_release()


__all__ = ["HoldHotkey"]
