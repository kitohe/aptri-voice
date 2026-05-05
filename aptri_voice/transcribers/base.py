"""Backend-agnostic Whisper transcriber Protocol."""
from __future__ import annotations

from typing import Protocol

import numpy as np


class TranscriberLike(Protocol):
    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str: ...


__all__ = ["TranscriberLike"]
