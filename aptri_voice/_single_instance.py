"""Single-instance guard.

Two concurrent aptri-voice processes both grab the global hotkey and both type
into the focused window, producing interleaved/duplicated output (e.g. "Hei."
typed by two instances becomes "HeiHei."). This refuses to start a second
instance.

We hold an exclusive *advisory* lock on a file in the temp dir for the lifetime
of the process. The OS releases the lock automatically when the process exits -
even on crash or SIGKILL - so there is no stale lock to clean up. The holder's
pid is written into the file (in an unlocked region) purely for diagnostics.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

_LOCK_PATH = Path(tempfile.gettempdir()) / "aptri-voice.lock"

# On Windows msvcrt locks a byte range; lock a byte well past the pid text so the
# pid stays readable by other instances. On POSIX flock locks the whole fd and
# this offset is ignored.
_LOCK_OFFSET = 1024


class AlreadyRunning(RuntimeError):
    """Raised when another instance already holds the lock."""

    def __init__(self, pid: Optional[int]) -> None:
        self.pid = pid
        who = f" (pid {pid})" if pid else ""
        super().__init__(f"aptri-voice is already running{who}")


class SingleInstance:
    """Acquire on construction; hold for the process lifetime.

    Raises AlreadyRunning if another instance holds the lock.
    """

    def __init__(self, path: Path = _LOCK_PATH) -> None:
        self._path = path
        self._fd: Optional[int] = None
        self._acquire()

    def _read_pid(self) -> Optional[int]:
        # Separate read-only open; the pid lives in an unlocked region.
        try:
            return int(self._path.read_text().split()[0])
        except Exception:
            return None

    def _acquire(self) -> None:
        fd = os.open(self._path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            _lock(fd)
        except OSError:
            pid = self._read_pid()
            os.close(fd)
            raise AlreadyRunning(pid)
        # We hold the lock: record our pid (unlocked region, bytes 0..N).
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            os.ftruncate(fd, 0)
            os.write(fd, f"{os.getpid()}\n".encode())
            os.fsync(fd)
        except OSError:
            pass  # diagnostics only; lock is what matters
        self._fd = fd

    def release(self) -> None:
        if self._fd is not None:
            try:
                _unlock(self._fd)
            finally:
                os.close(self._fd)
                self._fd = None

    def __enter__(self) -> "SingleInstance":
        return self

    def __exit__(self, *_exc) -> None:
        self.release()


if sys.platform == "win32":
    import msvcrt

    def _lock(fd: int) -> None:
        os.lseek(fd, _LOCK_OFFSET, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)  # non-blocking; OSError if held

    def _unlock(fd: int) -> None:
        try:
            os.lseek(fd, _LOCK_OFFSET, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
else:
    import fcntl

    def _lock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # OSError if held

    def _unlock(fd: int) -> None:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass


__all__ = ["SingleInstance", "AlreadyRunning"]
