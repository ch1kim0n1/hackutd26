"""Spectrum/waterfall data models — docs/04 RF contract + provenance."""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SourceMode(str, Enum):
    LIVE = "live"            # measured IQ from attached SDR, just now
    RECORDED = "recorded"    # replay of a previously captured IQ file
    SYNTHETIC = "synthetic"  # generated test signal — NEVER a measurement


@dataclass
class SpectrumFrame:
    """One FFT row. Fields are exactly the docs/04 SDR FFT contract."""
    center_frequency_hz: float
    sample_rate_hz: float
    fft_size: int
    bin_width_hz: float
    dbfs_bins: list[float]
    window_type: str
    receiver_id: str
    observed_at: str
    source_mode: SourceMode
    iq_provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "center_frequency_hz": self.center_frequency_hz,
            "sample_rate_hz": self.sample_rate_hz,
            "fft_size": self.fft_size,
            "bin_width_hz": self.bin_width_hz,
            "dbfs_bins": self.dbfs_bins,
            "window_type": self.window_type,
            "receiver_id": self.receiver_id,
            "observed_at": self.observed_at,
            "source_mode": self.source_mode.value,
            "iq_provenance": self.iq_provenance,
        }


@dataclass
class Waterfall:
    """Ordered FFT rows + axis metadata. Rendering is downstream."""
    receiver_id: str
    source_mode: SourceMode
    start_epoch: float
    frames: list[SpectrumFrame]
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def frequency_axis(self) -> tuple[float, float]:
        f = self.frames[0]
        half = f.sample_rate_hz / 2
        return (f.center_frequency_hz - half, f.center_frequency_hz + half)

    def to_dict(self) -> dict:
        return {
            "type": "sdr_waterfall",
            "provenance": {
                "source_mode": self.source_mode.value,
                "receiver_id": self.receiver_id,
                "generated_at": time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "is_measurement": self.source_mode == SourceMode.LIVE,
                "warning": None if self.source_mode == SourceMode.LIVE
                    else "NOT a live measurement — do not present as spectrum "
                         "evidence of real RF environment",
            },
            "axes": {
                "frequency": {"unit": "Hz", "span_hz": self.frames[0].sample_rate_hz,
                              "min_hz": self.frequency_axis[0],
                              "max_hz": self.frequency_axis[1],
                              "bin_width_hz": self.frames[0].bin_width_hz},
                "time": {"unit": "s", "rows": len(self.frames),
                         "row_period_s": self.meta.get("row_period_s")},
            },
            "frames": [f.to_dict() for f in self.frames],
        }


@dataclass
class ChannelActivity:
    """P0 fallback — Wi-Fi channel activity view. NOT a spectrum."""
    zone_id: str
    generated_at: str
    source_mode: SourceMode
    channels: dict[int, dict[str, Any]]  # channel -> counts/rssi stats
    ap_count: int
    notes: str = "Wi-Fi AP observation activity — not an RF spectrum waterfall"

    def to_dict(self) -> dict:
        return {
            "type": "wifi_channel_activity",
            "zone_id": self.zone_id,
            "generated_at": self.generated_at,
            "source_mode": self.source_mode.value,
            "ap_count": self.ap_count,
            "channels": {str(k): v for k, v in self.channels.items()},
            "notes": self.notes,
        }
