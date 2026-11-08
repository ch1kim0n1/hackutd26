# RF engineering handoff (#40)

## What exists

- `sensors/` — puck cores (A: Wi-Fi scan, B: reed+debounce+maintenance,
  C: enrolled-BLE-only), HMAC event signing, collector auth+staleness,
  ESP-IDF firmware skeletons.
- `sensors/correlator/` — adapters for Kismet/ESP32/puck events,
  dedup, RF01/PHY01/CORR01 rules, maintenance suppression,
  evidence-quality incident candidates.
- `sensors/sdr/` — IQ sources (synthetic/recorded/live-gated),
  windowed FFT→dBFS waterfall, LIVE/RECORDED/SYNTHETIC provenance,
  rtl-sdr 2.4 GHz rejection, channel-activity fallback.

## Integration touchpoints (docs/04)

- Puck/correlator events → collector relay → `observations`/
  `rf_frames` tables; correlator candidates → `incidents` queue.
- SDR waterfall artifacts → protected `evidence` store (provenance
  mandatory — synthetic never labeled live).
- RF/AP anomalies are *possible wireless anomaly* evidence only —
  never proof of exfiltration (scope matrix #26 enforces).

## Known limitations / risks

- **No radios available** — all RF paths tested on fixtures/synthetic
  IQ; Kismet field names, ESP32 radio behavior, RTL-SDR capture are
  unverified against real hardware.
- Channel plans, RSSI thresholds, debounce windows are placeholders
  pending site survey.
- Correlator rules tuned on fixtures — expect recalibration on live RF.

## Next steps

1. Deploy puck firmware on ESP32s; verify HMAC event flow to collector.
2. Connect live Kismet; validate adapter field mapping.
3. Attach RTL-SDR; run `sensors/sdr` live mode; calibrate dBFS floor.
4. Replay recorded captures through correlator; tune RF01/PHY01/CORR01.
