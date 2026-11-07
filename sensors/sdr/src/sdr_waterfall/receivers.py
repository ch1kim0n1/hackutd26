"""Receiver capability registry + honest band guard.

The critical honesty rule (docs/03): a generic RTL-SDR dongle is NOT a
2.4 GHz Wi-Fi receiver. Supported bands are declared per receiver model;
requests outside them are rejected, not silently attempted."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

WIFI_24GHZ = (2_400_000_000, 2_483_500_000)


class UnsupportedBand(Exception):
    pass


@dataclass
class Receiver:
    receiver_id: str
    model: str
    min_hz: float
    max_hz: float
    max_sample_rate_hz: float
    iq_format: str          # e.g. "cs8", "cu8"
    live_capable: bool
    notes: str = ""

    def check_band(self, center_hz: float, sample_rate_hz: float) -> None:
        lo = center_hz - sample_rate_hz / 2
        hi = center_hz + sample_rate_hz / 2
        if hi < self.min_hz or lo > self.max_hz:
            raise UnsupportedBand(
                f"{self.receiver_id} ({self.model}) cannot tune "
                f"{center_hz/1e6:.1f} MHz ±{sample_rate_hz/2e6:.1f} MHz "
                f"(range {self.min_hz/1e6:.0f}-{self.max_hz/1e6:.0f} MHz). "
                f"{self.notes}")
        if sample_rate_hz > self.max_sample_rate_hz:
            raise UnsupportedBand(
                f"sample_rate {sample_rate_hz/1e6:.2f} MS/s exceeds "
                f"{self.receiver_id} max {self.max_sample_rate_hz/1e6:.2f} MS/s")
        if WIFI_24GHZ[0] <= center_hz <= WIFI_24GHZ[1] and self.model.startswith("rtl-sdr"):
            raise UnsupportedBand(
                "generic RTL-SDR cannot capture 2.4 GHz Wi-Fi spectrum "
                "(docs/03). Use a supported sub-GHz emitter band or a "
                "wideband receiver (e.g. HackRF/Pluto) configured here.")


def load_receivers(path: str | Path) -> dict[str, Receiver]:
    raw = json.loads(Path(path).read_text())
    return {
        rid: Receiver(
            receiver_id=rid, model=r["model"],
            min_hz=float(r["min_hz"]), max_hz=float(r["max_hz"]),
            max_sample_rate_hz=float(r["max_sample_rate_hz"]),
            iq_format=r.get("iq_format", "cs8"),
            live_capable=bool(r.get("live_capable", False)),
            notes=r.get("notes", ""),
        )
        for rid, r in raw["receivers"].items()
    }
