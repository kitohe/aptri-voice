"""Backend selection for the Whisper transcriber.

`device_mode`:
    auto  - MLX on Apple Silicon, else CUDA torch, else CPU torch
    mlx   - force mlx-whisper (Apple Silicon only)
    cuda  - force CUDA torch (falls back to CPU if unavailable)
    cpu   - force CPU torch
"""
from __future__ import annotations

import importlib.util
import logging
import platform
from typing import Optional

from .base import TranscriberLike

log = logging.getLogger(__name__)


def _is_apple_silicon() -> bool:
    return platform.system() == "Darwin" and platform.machine() == "arm64"


def _mlx_available() -> bool:
    return importlib.util.find_spec("mlx_whisper") is not None


def _resolve_auto() -> str:
    if _is_apple_silicon() and _mlx_available():
        return "mlx"
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
    except ImportError:
        pass
    return "cpu"


def build_transcriber(
    device_mode: str = "auto",
    model_id: Optional[str] = None,
    language: Optional[str] = None,
) -> TranscriberLike:
    if device_mode == "auto":
        device_mode = _resolve_auto()
        log.info("Auto-selected backend: %s", device_mode)

    if device_mode == "mlx":
        if not _is_apple_silicon():
            raise RuntimeError(
                "MLX backend requires macOS on Apple Silicon (arm64)."
            )
        if not _mlx_available():
            raise RuntimeError(
                "mlx-whisper is not installed. Run: pip install -e \".[mlx]\""
            )
        from .mlx import MLXTranscriber, DEFAULT_MODEL_ID as MLX_DEFAULT
        return MLXTranscriber(
            model_id=model_id or MLX_DEFAULT,
            language=language,
        )

    if device_mode in ("cuda", "cpu"):
        from .torch_hf import TorchHFTranscriber, DEFAULT_MODEL_ID as TORCH_DEFAULT
        return TorchHFTranscriber(
            model_id=model_id or TORCH_DEFAULT,
            device=device_mode,
            language=language,
        )

    raise ValueError(f"Unknown device_mode: {device_mode!r}")


__all__ = ["build_transcriber"]
