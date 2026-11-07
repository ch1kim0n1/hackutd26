# SDR IQ/FFT capture — honest provenance (issue #15)

Optional true-spectrum path per `docs/03-ROBOTICS-RF.md` waterfall
correctness rules + `docs/04` SDR FFT contract. **P0 channel-activity
fallback stays separate and is never labeled spectrum.**

## Honesty model

Every `SpectrumFrame`/`Waterfall` carries `source_mode`:

| Mode | Meaning | May be shown as |
|---|---|---|
| `live` | measured IQ from attached SDR *now* | true spectrum (with axes) |
| `recorded` | replay of a captured IQ file | labeled replay |
| `synthetic` | generated test signal | test/demo only — `is_measurement:false`, warning embedded |

`Waterfall.to_dict()` embeds `provenance.is_measurement` and a warning
string for non-live modes — downstream dashboards cannot accidentally
render synthetic data as real spectrum.

## The 2.4 GHz rule

`receivers.py` + `config/receivers.json` declare per-model bands.
`Receiver.check_band()` **rejects** requests outside range, over
`max_sample_rate_hz`, or 2.4 GHz Wi-Fi on `rtl-sdr*` models — the docs/03
rule that a generic RTL-SDR dongle is not a 2.4 GHz Wi-Fi receiver.
HackRF/Pluto entries exist but `live_capable:false` until actually
deployed + calibrated.

## IQ sources (`iq_sources.py`)

- `SyntheticIqSource` — deterministic tones+noise (tests/demo)
- `FileIqSource` — `.cf32`/`.npy` replay → `RECORDED`
- `LiveIqSource` — requires `live_capable:true` + SoapySDR/pyrtlsdr +
  hardware; raises `HardwareUnavailable` otherwise. **Never fabricates
  live data.**

## FFT (`fft.py`)

Windowed FFT (hann/hamming/blackman/rect, coherent-gain normalized) →
dBFS bins. `SpectrumFrame` carries the full docs/04 contract:
`center_frequency_hz, sample_rate_hz, fft_size, bin_width_hz,
dbfs_bins[], window_type, receiver_id, observed_at, source_mode` plus
`iq_provenance`. `Waterfall` adds explicit frequency/time axes.

## P0 fallback (`channel_activity.py`)

`channel_activity()` builds the Wi-Fi channel activity view from
`wifi_ap_seen` observations: per-channel observation counts, unique
BSSID counts, SSID sets, RSSI min/max/mean. Notes field states it is
**not** an RF spectrum waterfall.

## Usage

```sh
cd sensors/sdr
pip install -e '.[dev]'   # live capture: pip install -e '.[live]'
PYTHONPATH=src python3 -m pytest tests/ -q     # 10 tests

# synthetic waterfall (demo only)
python3 -m sdr_waterfall waterfall --synthetic --center 433920000 \
    --rate 2400000 --fft 1024 --rows 16 --out wf.json

# replay captured IQ
python3 -m sdr_waterfall waterfall --file capture.cf32 \
    --rate 2500000 --center 433920000 --rows 32

# enforce receiver capability (rejects rtl-sdr @ 2.4 GHz)
python3 -m sdr_waterfall waterfall --synthetic --center 2437000000 \
    --rate 20000000 --receiver rtl-sdr-01   # -> error, exit 3

# P0 channel activity from puck observations
python3 -m sdr_waterfall activity obs.jsonl --zone rack-01 --out act.json
```

## Evidence

- `evidence/synthetic-waterfall-433mhz.json` — 16-row synthetic
  waterfall @ 433.92 MHz, `source_mode:synthetic`, warning embedded.
- `evidence/channel-activity-rack01.json` — channel activity view from
  fixture observations (labeled `live` input mode; content is fixture
  data, not a measurement).

## Integration (docs/04)

- `SpectrumFrame.to_dict()` matches the `rf_frames`/SDR FFT contract;
  `source_mode` maps to `live|replay|synthetic` provenance required for
  evidence trust tiers.
- Channel activity consumes the same `wifi_ap_seen` observations as the
  correlator (issue #14) — shared upstream collector.

## NOT done — needs hardware

- No SDR attached; `LiveIqSource.read()` raises `HardwareUnavailable`.
  SoapySDR/pyrtlsdr integration is scaffolded, not validated.
- No real IQ captures exist yet; `FileIqSource` tested on synthetic
  `.cf32` written by numpy.
- Antenna selection, gain calibration, and band verification pending
  physical bring-up. rtl_433 decodes specific ISM protocols only — it is
  not wired in here and does not provide spectrum.
