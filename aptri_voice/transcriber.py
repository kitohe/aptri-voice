"""Whisper transcription via Hugging Face transformers.

Loads `openai/whisper-large-v3-turbo` directly. Uses CUDA fp16 when available,
falls back to CPU fp32. Designed for push-to-talk: model is loaded once,
transcribe() is the hot path.
"""
from __future__ import annotations

import logging
import os
import warnings
from typing import Optional

import numpy as np

os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
warnings.filterwarnings("ignore", message=".*Triton.*")

# Silence the per-file HEAD probe spam from `transformers.from_pretrained` and
# the "unauthenticated requests" warning from huggingface_hub. These fire even
# for fully-cached models and have nothing to do with our work.
for _name in ("httpx", "httpcore", "urllib3", "huggingface_hub.utils._http"):
    logging.getLogger(_name).setLevel(logging.WARNING)

import torch  # noqa: E402
import transformers  # noqa: E402
from transformers import AutoProcessor, WhisperForConditionalGeneration  # noqa: E402

# Drop transformers' own info/warning chatter ("forced_decoder_ids deprecated",
# "max_new_tokens vs max_length", "custom logits processor", etc.). They're
# benign and identical on every call.
transformers.logging.set_verbosity_error()

log = logging.getLogger(__name__)

DEFAULT_MODEL_ID = "openai/whisper-large-v3-turbo"

# Whisper's hard cap is 448 tokens per 30s window; leave headroom for prompt tokens.
_MAX_NEW_TOKENS = 440
# transformers silently truncates >30s clips unless return_timestamps=True.
_LONG_FORM_THRESHOLD_S = 30.0


def _pick_device_and_dtype(device: Optional[str]) -> tuple[str, "torch.dtype"]:
    if device is None or device == "auto":
        if torch.cuda.is_available():
            return "cuda", torch.float16
        return "cpu", torch.float32

    if device == "cuda":
        if not torch.cuda.is_available():
            log.warning("CUDA requested but not available; falling back to CPU.")
            return "cpu", torch.float32
        return "cuda", torch.float16
    if device == "cpu":
        return "cpu", torch.float32
    raise ValueError(f"Unknown device: {device!r}")


class Transcriber:
    """Push-to-talk Whisper transcriber backed by HF transformers."""

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        device: Optional[str] = None,
        language: Optional[str] = None,
    ) -> None:
        self.model_id = model_id
        self.device, self.dtype = _pick_device_and_dtype(device)
        self.language = language

        log.info("Loading %s on device=%s dtype=%s", model_id, self.device, self.dtype)

        self.processor, self.model = self._load(model_id)
        self.model.to(self.device)
        self.model.eval()

        self._warmup()

    def _load(self, model_id: str):
        # Try fully offline first: if the model is already cached, this skips
        # the ~15 HEAD requests transformers does to validate the cache. On a
        # cache miss it raises, and we retry online to download.
        for offline in (True, False):
            try:
                processor = AutoProcessor.from_pretrained(
                    model_id, local_files_only=offline
                )
                model = WhisperForConditionalGeneration.from_pretrained(
                    model_id,
                    dtype=self.dtype,
                    attn_implementation="sdpa",
                    low_cpu_mem_usage=True,
                    local_files_only=offline,
                )
                if offline:
                    log.debug("Loaded from local cache (no network).")
                return processor, model
            except (OSError, ValueError) as exc:
                if offline:
                    log.info("Cache miss for %s; downloading...", model_id)
                    continue
                raise
        raise RuntimeError("unreachable")

    def _warmup(self) -> None:
        try:
            silent = np.zeros(16000, dtype=np.float32)
            self.transcribe(silent)
            log.debug("Warmup complete.")
        except Exception as exc:
            log.warning("Warmup failed (non-fatal): %s", exc)

    @torch.inference_mode()
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

        inputs = self.processor(
            audio,
            sampling_rate=sample_rate,
            return_tensors="pt",
        )
        feats = inputs.input_features.to(self.device, dtype=self.dtype)

        long_form = (audio.shape[0] / sample_rate) > _LONG_FORM_THRESHOLD_S
        gen_kwargs: dict = {
            "max_new_tokens": _MAX_NEW_TOKENS,
            "num_beams": 1,
            "do_sample": False,
            "condition_on_prev_tokens": False,
            "temperature": 0.0,
            "return_timestamps": long_form,
        }
        if self.language:
            gen_kwargs["language"] = self.language
            gen_kwargs["task"] = "transcribe"

        ids = self.model.generate(feats, **gen_kwargs)
        text = self.processor.batch_decode(ids, skip_special_tokens=True)[0]
        return text.strip()


__all__ = ["Transcriber"]
