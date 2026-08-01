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
MAX_DURATION_S = 300.0
MIN_DURATION_S = 0.30

# Guards PortAudio's global lifecycle. Pa_Terminate() force-closes open streams,
# so a refresh must never overlap a stream teardown.
_PA_LOCK = threading.Lock()


def _reinit_portaudio() -> None:
    """Rebuild PortAudio's snapshot of the system audio devices.

    PortAudio enumerates devices exactly once, inside Pa_Initialize(), which
    sounddevice calls at import and never again. macOS sleep/wake destroys and
    re-creates every CoreAudio device object, so the cached AudioDeviceIDs go
    stale: opening a stream then hands AUHAL a dead device and fails with
    paInternalError (-9986) for the rest of the process's life. Re-initializing
    takes a fresh snapshot in ~3 ms.

    These are sounddevice private helpers - it exposes no public equivalent.
    """
    with _PA_LOCK:
        sd._terminate()
        sd._initialize()


def resolve_input_device(spec: int | str | None) -> int | str | None:
    """Pin a device selection to something that survives a device-table refresh.

    A PortAudio index is only meaningful inside one Pa_Initialize() snapshot -
    sounddevice passes ints through without validating them. If devices appeared
    or disappeared while the machine slept, index N comes back pointing at a
    different microphone. Names survive, and sounddevice re-resolves a name on
    every open, so we translate the selection to an exact device name once and use
    that from then on.

    ``None`` is left alone: it means "whatever the system default is", which
    should keep following the default across a refresh.

    Raises ValueError or sd.PortAudioError if the selection names no input device.
    """
    if spec is None:
        return None
    info = sd.query_devices(spec, "input")
    hostapis = [h["name"] for h in sd.query_hostapis()]
    inputs = [d for d in sd.query_devices() if d["max_input_channels"] > 0]

    name = info["name"]
    if sum(1 for d in inputs if d["name"] == name) == 1:
        return name

    # Windows exposes one microphone once per host API (MME, DirectSound, WASAPI,
    # WDM-KS) under a single name, so a bare name identifies nothing there. macOS
    # has only Core Audio and never hits this. sounddevice also matches
    # "<name>, <host api>", which is unique per device.
    qualified = f"{name}, {hostapis[info['hostapi']]}"
    if sum(1 for d in inputs if f"{d['name']}, {hostapis[d['hostapi']]}" == qualified) == 1:
        return qualified

    # Two identical mics on one host API: the index is all that separates them.
    log.warning(
        "input device %r is ambiguous even with its host API; keeping index %r, which "
        "may point elsewhere if devices change while the machine is asleep",
        name,
        spec,
    )
    return spec


@dataclass
class RecordResult:
    audio: np.ndarray
    duration_s: float
    too_short: bool


class Recorder:
    """Streaming mic capture; start()/stop() returns a RecordResult."""

    def __init__(self, device: Optional[int | str] = None) -> None:
        self._device = resolve_input_device(device)
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
            try:
                self._open_stream()
            except sd.PortAudioError:
                # Usually a stale device table after the machine slept; also covers
                # a mic that was unplugged and replugged. Refresh and retry once so
                # the user never has to restart the app. _pick_sample_rate() reads
                # the same stale table, so the whole open is retried, not just the
                # InputStream call.
                log.warning("could not open input stream; refreshing audio devices")
                _reinit_portaudio()
                self._open_stream()

    def _open_stream(self) -> None:
        self._chunks = []
        self._frames_captured = 0
        self._sample_rate = self._pick_sample_rate()
        self._max_frames = int(MAX_DURATION_S * self._sample_rate)
        stream = sd.InputStream(
            samplerate=self._sample_rate,
            channels=1,
            dtype=TARGET_DTYPE,
            device=self._device,
            callback=self._callback,
            blocksize=0,
        )
        try:
            stream.start()
        except BaseException:
            stream.close()
            raise
        # Publish only once running, so a failed open leaves the recorder idle and
        # retryable instead of wedged behind the `self._stream is not None` guard.
        self._stream = stream

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

        # Serialise teardown against _reinit_portaudio(): the hotkey thread may be
        # in start() refreshing PortAudio, and Pa_Terminate() would close this
        # stream out from under us.
        with _PA_LOCK:
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


__all__ = [
    "Recorder",
    "RecordResult",
    "MIN_DURATION_S",
    "TARGET_SR",
    "resolve_input_device",
]
