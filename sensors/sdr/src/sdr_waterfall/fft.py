"""Windowed FFT -> dBFS bins (docs/04 SDR FFT contract)."""
from __future__ import annotations

import numpy as np

WINDOWS = {"hann": np.hanning, "hamming": np.hamming,
           "blackman": np.blackman, "rect": lambda n: np.ones(n)}


def fft_to_dbfs(iq: np.ndarray, fft_size: int, window_type: str = "hann"
                ) -> tuple[list[float], float]:
    """Returns (dbfs_bins, bin_width_hz_placeholder) — caller supplies rate."""
    n = min(len(iq), fft_size)
    seg = iq[:n]
    if len(seg) < fft_size:
        seg = np.pad(seg, (0, fft_size - len(seg)))
    win = WINDOWS[window_type](fft_size).astype(np.float64)
    win /= win.mean()  # coherent-gain normalize so tones read ~0 dBFS
    spec = np.fft.fftshift(np.fft.fft(seg * win))
    power = np.abs(spec) ** 2
    # normalize to full-scale sine -> dBFS
    ref = (fft_size ** 2) / 4.0
    db = 10.0 * np.log10(power / ref + 1e-20)
    return [float(x) for x in db], 0.0


def spectrum_frame(iq: np.ndarray, sample_rate_hz: float,
                   center_frequency_hz: float, fft_size: int,
                   window_type: str, receiver_id: str,
                   observed_at: str, source_mode, provenance: dict):
    from .models import SpectrumFrame
    db, _ = fft_to_dbfs(iq, fft_size, window_type)
    return SpectrumFrame(
        center_frequency_hz=center_frequency_hz,
        sample_rate_hz=sample_rate_hz,
        fft_size=fft_size,
        bin_width_hz=sample_rate_hz / fft_size,
        dbfs_bins=db,
        window_type=window_type,
        receiver_id=receiver_id,
        observed_at=observed_at,
        source_mode=source_mode,
        iq_provenance=provenance,
    )
