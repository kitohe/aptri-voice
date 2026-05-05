"""Whisper transcription via MLX on Apple Silicon.

Wraps `mlx_whisper.transcribe`, which accepts a numpy float32 mono 16 kHz
buffer directly and handles long-form chunking internally. Weights are
pulled from the `mlx-community` HF org (pre-converted; no torch needed).
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)

DEFAULT_MODEL_ID = "mlx-community/whisper-large-v3-turbo"


class MLXTranscriber:
    """Push-to-talk Whisper transcriber backed by mlx-whisper."""

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        language: Optional[str] = None,
        fp16: bool = True,
    ) -> None:
        # Import lazily so non-Apple platforms don't pay the import cost
        # and don't fail at module load when the wheel isn't installed.
        import mlx_whisper

        self._mlx_whisper = mlx_whisper
        self.model_id = model_id
        self.language = language
        self.fp16 = fp16

        log.info("Loading %s via mlx-whisper (fp16=%s)", model_id, fp16)
        self._warmup()

    def _warmup(self) -> None:
        try:
            silent = np.zeros(16000, dtype=np.float32)
            self.transcribe(silent)
            log.debug("Warmup complete.")
        except Exception as exc:
            log.warning("Warmup failed (non-fatal): %s", exc)

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        if audio is None or audio.size == 0:
            return ""

        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)
        if audio.ndim > 1:
            audio = audio.mean(axis=-1).astype(np.float32, copy=False)
        if sample_rate != 16000:
            raise ValueError(
                f"Expected 16000 Hz audio, got {sample_rate}. "
                "Resample upstream before calling transcribe()."
            )

        kwargs: dict = {
            "path_or_hf_repo": self.model_id,
            "fp16": self.fp16,
            "condition_on_previous_text": False,
            "temperature": 0.0,
            "verbose": None,
        }
        if self.language:
            kwargs["language"] = self.language
            kwargs["task"] = "transcribe"

        result = self._mlx_whisper.transcribe(audio, **kwargs)
        return result["text"].strip()


__all__ = ["MLXTranscriber", "DEFAULT_MODEL_ID"]
