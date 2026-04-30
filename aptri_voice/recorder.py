"""Mic capture at 16 kHz mono float32 (Whisper-native), with safety cap."""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from math import gcd
from typing import Optional

import numpy as np
import sounddevice as sd
from scipy.signal import resample_poly

log = logging.getLogger(__name__)

TARGET_SR = 16_000
TARGET_DTYPE = "float32"
MAX_DURATION_S = 60.0
MIN_DURATION_S = 0.30


@dataclass
class RecordResult:
    audio: np.ndarray
    duration_s: float
    too_short: bool


class Recorder:
    """Streaming mic capture; start()/stop() returns a RecordResult."""

    def __init__(self, device: Optional[int | str] = None) -> None:
        self._device = device
        self._stream: Optional[sd.InputStream] = None
        self._chunks: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._sample_rate: int = TARGET_SR
        self._max_frames: int = int(MAX_DURATION_S * TARGET_SR)
        self._frames_captured = 0

    @staticmethod
    def list_input_devices() -> list[dict]:
        devs = sd.query_devices()
        return [
            {"index": i, "name": d["name"], "default_sr": int(d["default_samplerate"])}
            for i, d in enumerate(devs)
            if d["max_input_channels"] > 0
        ]

    def _pick_sample_rate(self) -> int:
        try:
            sd.check_input_settings(
                device=self._device,
                samplerate=TARGET_SR,
                channels=1,
                dtype=TARGET_DTYPE,
            )
            return TARGET_SR
        except Exception:
            info = sd.query_devices(self._device, "input")
            return int(info["default_samplerate"])

    def start(self) -> None:
        with self._lock:
            if self._stream is not None:
                return
            self._chunks = []
            self._frames_captured = 0
            self._sample_rate = self._pick_sample_rate()
            self._max_frames = int(MAX_DURATION_S * self._sample_rate)
            self._stream = sd.InputStream(
                samplerate=self._sample_rate,
                channels=1,
                dtype=TARGET_DTYPE,
                device=self._device,
                callback=self._callback,
                blocksize=0,
            )
            self._stream.start()

    def _callback(self, indata, frames, time_info, status) -> None:
        if status:
            log.warning("recorder stream status: %s", status)
        if self._frames_captured >= self._max_frames:
            return
        # PortAudio reuses the buffer; copy required.
        self._chunks.append(indata[:, 0].copy())
        self._frames_captured += frames

    def stop(self) -> RecordResult:
        with self._lock:
            stream = self._stream
            self._stream = None
        if stream is None:
            return RecordResult(np.zeros(0, dtype=np.float32), 0.0, True)

        stream.stop()
        stream.close()

        if not self._chunks:
            return RecordResult(np.zeros(0, dtype=np.float32), 0.0, True)

        audio = np.concatenate(self._chunks).astype(np.float32, copy=False)
        audio = audio[: self._max_frames]
        duration = audio.shape[0] / self._sample_rate

        if self._sample_rate != TARGET_SR:
            g = gcd(self._sample_rate, TARGET_SR)
            up = TARGET_SR // g
            down = self._sample_rate // g
            audio = resample_poly(audio, up, down).astype(np.float32, copy=False)

        return RecordResult(
            audio=audio,
            duration_s=duration,
            too_short=duration < MIN_DURATION_S,
        )


__all__ = ["Recorder", "RecordResult", "MIN_DURATION_S", "TARGET_SR"]
