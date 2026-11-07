"""Waterfall assembly: pull IQ chunks from a source, FFT each into a row,
return a Waterfall with explicit provenance + axes."""
from __future__ import annotations

import time

import numpy as np

from .fft import spectrum_frame
from .iq_sources import IqSource
from .models import SourceMode, Waterfall


def capture_waterfall(source: IqSource, fft_size: int = 1024,
                      rows: int = 32, window_type: str = "hann",
                      chunk_factor: int = 4) -> Waterfall:
    """chunk_factor: overlap factor for smoother time axis (rows advance
    by fft_size/chunk_factor samples)."""
    frames = []
    step = max(1, fft_size // chunk_factor)
    carry = None
    produced = 0
    t0 = time.time()
    while produced < rows:
        need = fft_size if carry is None else step
        chunk = source.read(need)
        if chunk is None:
            break
        buf = chunk.samples if carry is None else np.concatenate([carry, chunk.samples])
        if len(buf) < fft_size:
            carry = buf
            continue
        seg = buf[:fft_size]
        carry = buf[step:step + fft_size] if len(buf) >= step + fft_size else None
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        frames.append(spectrum_frame(
            seg, chunk.sample_rate_hz, chunk.center_frequency_hz,
            fft_size, window_type, source.receiver_id, ts,
            source.source_mode, chunk.provenance))
        produced += 1
    return Waterfall(
        receiver_id=source.receiver_id,
        source_mode=source.source_mode,
        start_epoch=t0,
        frames=frames,
        meta={"row_period_s": fft_size / source.sample_rate_hz
              if hasattr(source, "sample_rate_hz") else None,
              "fft_size": fft_size, "window_type": window_type,
              "overlap_step": step},
    )
