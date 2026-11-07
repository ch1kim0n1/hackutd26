import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from sdr_waterfall import (
    ChannelActivity,
    FileIqSource,
    HardwareUnavailable,
    LiveIqSource,
    Receiver,
    SourceMode,
    SpectrumFrame,
    SyntheticIqSource,
    UnsupportedBand,
    Waterfall,
    capture_waterfall,
    channel_activity,
    load_receivers,
)
from sdr_waterfall.fft import fft_to_dbfs, spectrum_frame

ROOT = Path(__file__).parents[1]


def test_fft_bin_width_and_dbfs_range():
    src = SyntheticIqSource(sample_rate_hz=2.4e6, center_frequency_hz=433.92e6,
                            tones_hz=[100e3], snr_db=30)
    chunk = src.read(4096)
    db, _ = fft_to_dbfs(chunk.samples, 1024, "hann")
    assert len(db) == 1024
    # bin width = rate/fft
    bw = 2.4e6 / 1024
    # tone at +100kHz -> bin index ~ (100k/bw) + 512 after fftshift
    peak_idx = int(np.argmax(db))
    assert abs((peak_idx - 512) * bw - 100e3) < bw * 1.5
    assert max(db) > -20  # strong synthetic tone visible
    assert min(db) > -120  # dBFS floor sane


def test_spectrum_frame_contract_fields():
    src = SyntheticIqSource()
    chunk = src.read(2048)
    f = spectrum_frame(chunk.samples, chunk.sample_rate_hz,
                       chunk.center_frequency_hz, 1024, "hann",
                       "synthetic-gen", "2026-11-07T20:00:00Z",
                       SourceMode.SYNTHETIC, chunk.provenance)
    d = f.to_dict()
    for k in ("center_frequency_hz", "sample_rate_hz", "fft_size",
              "bin_width_hz", "dbfs_bins", "window_type", "receiver_id",
              "observed_at", "source_mode"):
        assert k in d
    assert d["bin_width_hz"] == pytest.approx(d["sample_rate_hz"] / 1024)
    assert d["source_mode"] == "synthetic"


def test_waterfall_provenance_and_axes():
    src = SyntheticIqSource(sample_rate_hz=1e6, center_frequency_hz=433.92e6)
    wf = capture_waterfall(src, fft_size=256, rows=4, chunk_factor=2)
    assert isinstance(wf, Waterfall) and len(wf.frames) == 4
    d = wf.to_dict()
    assert d["provenance"]["source_mode"] == "synthetic"
    assert d["provenance"]["is_measurement"] is False
    assert "NOT a live measurement" in d["provenance"]["warning"]
    ax = d["axes"]["frequency"]
    assert ax["min_hz"] == pytest.approx(433.92e6 - 0.5e6)
    assert ax["max_hz"] == pytest.approx(433.92e6 + 0.5e6)


def test_rtl_sdr_rejects_2_4ghz():
    recvs = load_receivers(ROOT / "config" / "receivers.json")
    rtl = recvs["rtl-sdr-01"]
    # 433 MHz ISM OK
    rtl.check_band(433.92e6, 2.4e6)
    # 2.4 GHz Wi-Fi -> honest rejection
    with pytest.raises(UnsupportedBand, match="2.4 GHz Wi-Fi"):
        rtl.check_band(2.437e9, 20e6)
    # out of range entirely
    with pytest.raises(UnsupportedBand):
        rtl.check_band(5e9, 2e6)


def test_live_source_refuses_without_hardware():
    rtl = Receiver("rtl-sdr-01", "rtl-sdr", 0.5e6, 1.75e9, 2.5e6,
                   "cs8", live_capable=True)
    with pytest.raises(HardwareUnavailable):
        LiveIqSource(rtl, 433.92e6, 2.4e6)  # SoapySDR absent


def test_live_source_refuses_non_live_capable():
    hack = Receiver("hackrf-01", "hackrf-one", 1e6, 6e9, 20e6,
                    "cs8", live_capable=False)
    with pytest.raises(HardwareUnavailable, match="live_capable=false"):
        LiveIqSource(hack, 2.437e9, 20e6)


def test_file_iq_source_recorded_mode(tmp_path):
    iq = (np.random.default_rng(0).standard_normal(4096)
          + 1j * np.random.default_rng(1).standard_normal(4096)).astype(np.complex64)
    p = tmp_path / "test.cf32"
    iq.tofile(p)
    src = FileIqSource(p, sample_rate_hz=2.4e6,
                       center_frequency_hz=433.92e6)
    assert src.source_mode == SourceMode.RECORDED
    chunk = src.read(1024)
    assert chunk is not None and len(chunk.samples) == 1024
    assert chunk.provenance["format"] == ".cf32"
    # drain then EOF
    while src.read(4096):
        pass
    assert src.read(16) is None


def test_channel_activity_not_spectrum():
    obs = [
        {"kind": "wifi_ap_seen", "data": {"ssid": "A", "bssid": "01:00:00:00:00:01",
         "channel": 6, "rssi_dbm": -50}},
        {"kind": "wifi_ap_seen", "data": {"ssid": "A", "bssid": "01:00:00:00:00:01",
         "channel": 6, "rssi_dbm": -55}},
        {"kind": "wifi_ap_seen", "data": {"ssid": "B", "bssid": "01:00:00:00:00:02",
         "channel": 11, "rssi_dbm": -70}},
        {"kind": "cabinet_contact_open", "data": {}},  # ignored
    ]
    act = channel_activity(obs, "rack-01")
    assert isinstance(act, ChannelActivity)
    assert act.ap_count == 2
    assert act.channels[6]["observation_count"] == 2
    assert act.channels[6]["rssi_dbm_mean"] == pytest.approx(-52.5)
    assert act.channels[11]["unique_bssids"] == 1
    d = act.to_dict()
    assert "not an RF spectrum" in d["notes"]


def test_cli_synthetic_waterfall(tmp_path):
    out = tmp_path / "wf.json"
    r = subprocess.run(
        [sys.executable, "-m", "sdr_waterfall", "waterfall",
         "--synthetic", "--rows", "4", "--fft", "256", "--out", str(out)],
        env={"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin"},
        capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    d = json.loads(out.read_text())
    assert d["provenance"]["source_mode"] == "synthetic"
    assert len(d["frames"]) == 4


def test_cli_rejects_rtl_24ghz(tmp_path):
    out = tmp_path / "wf.json"
    r = subprocess.run(
        [sys.executable, "-m", "sdr_waterfall", "waterfall",
         "--synthetic", "--center", "2437000000", "--rate", "20000000",
         "--receiver", "rtl-sdr-01", "--out", str(out)],
        env={"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin"},
        capture_output=True, text=True)
    assert r.returncode == 3
    assert "2.4 GHz Wi-Fi" in r.stdout
