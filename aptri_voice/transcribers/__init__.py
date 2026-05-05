"""Backend-agnostic Whisper transcriber package."""
from .base import TranscriberLike
from .factory import build_transcriber

__all__ = ["TranscriberLike", "build_transcriber"]
