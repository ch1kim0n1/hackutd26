"""IQ sources. Live capture requires actual hardware; everything else is
honestly labeled RECORDED or SYNTHETIC.

- SyntheticIqSource: deterministic test tones — always source_mode=SYNTHETIC
- FileIqSource: replays a captured IQ file — source_mode=RECORDED
- LiveIqSource: shell-outs to SoapySDR/pyrtlsdr — raises HardwareUnavailable
  when the device/driver is absent. Never fabricates 'live' data."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import numpy as np

from .models import SourceMode


class HardwareUnavailable(RuntimeError):
    pass


@dataclass
class IqChunk:
    samples: np.ndarray          # complex64 IQ
    sample_rate_hz: float
    center_frequency_hz: float
    provenance: dict


class IqSource:
    source_mode: SourceMode = SourceMode.SYNTHETIC
    receiver_id: str = "synthetic"

    def read(self, n_samples: int) -> IqChunk | None:
        raise NotImplementedError


class SyntheticIqSource(IqSource):
    """Deterministic synthetic IQ: configurable tones + noise.
    Clearly NOT a measurement — used for pipeline tests/demo only."""

    source_mode = SourceMode.SYNTHETIC

    def __init__(self, sample_rate_hz: float = 2.4e6,
                 center_frequency_hz: float = 433.92e6,
                 tones_hz: list[float] | None = None,
                 snr_db: float = 20.0, seed: int = 7):
        self.sample_rate_hz = sample_rate_hz
        self.center_frequency_hz = center_frequency_hz
        self.tones_hz = tones_hz if tones_hz is not None else [100e3, -250e3]
        self.snr_db = snr_db
        self.rng = np.random.default_rng(seed)
        self.receiver_id = "synthetic-gen"
        self._t = 0

    def read(self, n: int) -> IqChunk:
        t = (self._t + np.arange(n)) / self.sample_rate_hz
        self._t += n
        sig = np.zeros(n, dtype=np.complex64)
        for f in self.tones_hz:
            sig += np.exp(2j * np.pi * f * t).astype(np.complex64)
        noise = (self.rng.standard_normal(n) +
                 1j * self.rng.standard_normal(n)).astype(np.complex64)
        noise *= np.sqrt(0.5 / (10 ** (self.snr_db / 10)))
        return IqChunk(sig + noise, self.sample_rate_hz,
                       self.center_frequency_hz,
                       {"kind": "synthetic_tones", "tones_hz": self.tones_hz,
                        "snr_db": self.snr_db, "seed": 7})


class FileIqSource(IqSource):
    """Replay a raw complex64 .cf32 IQ file (or .npy). RECORDED mode."""

    source_mode = SourceMode.RECORDED

    def __init__(self, path: str | Path, sample_rate_hz: float,
                 center_frequency_hz: float, receiver_id: str = "file-replay"):
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        self.sample_rate_hz = sample_rate_hz
        self.center_frequency_hz = center_frequency_hz
        self.receiver_id = receiver_id
        self._offset = 0
        self._data: np.ndarray | None = None
        self.provenance = {"file": str(self.path), "format": self.path.suffix}

    def _load(self) -> np.ndarray:
        if self._data is None:
            if self.path.suffix == ".npy":
                self._data = np.load(self.path).astype(np.complex64)
            else:
                raw = np.fromfile(self.path, dtype=np.complex64)
                self._data = raw
        return self._data

    def read(self, n: int) -> IqChunk | None:
        data = self._load()
        if self._offset >= len(data):
            return None
        chunk = data[self._offset:self._offset + n]
        self._offset += len(chunk)
        return IqChunk(chunk, self.sample_rate_hz,
                       self.center_frequency_hz,
                       {**self.provenance, "offset": self._offset})


class LiveIqSource(IqSource):
    """Real SDR capture via SoapySDR/pyrtlsdr — only when hardware exists."""

    source_mode = SourceMode.LIVE

    def __init__(self, receiver, center_frequency_hz: float,
                 sample_rate_hz: float, antenna: str = ""):
        self.receiver = receiver
        self.receiver_id = receiver.receiver_id
        self.center_frequency_hz = center_frequency_hz
        self.sample_rate_hz = sample_rate_hz
        self.antenna = antenna
        self._stream = None
        if not receiver.live_capable:
            raise HardwareUnavailable(
                f"{receiver.receiver_id} marked live_capable=false in "
                f"receiver config — refusing to pretend live capture")
        try:
            import SoapySDR  # noqa: F401
        except ImportError:
            raise HardwareUnavailable(
                "SoapySDR/pyrtlsdr not installed — no live IQ source. "
                "Install `.[live]` extras and attach supported SDR.")

    def read(self, n: int) -> IqChunk | None:
        if self._stream is None:
            raise HardwareUnavailable("live stream not yet opened")
        # Real implementation: soapysdr readStream into complex buffer.
        # Kept minimal — validated on hardware before demo use.
        raise HardwareUnavailable("live IQ read path unvalidated on hardware")
