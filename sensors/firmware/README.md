# Sensor puck firmware (ESP-IDF)

| Dir | Target | Role |
|---|---|---|
| `puck_a/` | ESP32-S3 | Wi-Fi scan → `wifi_ap_seen` |
| `puck_b/` | ESP32 | reed switch → `cabinet_contact_*` |
| `puck_c/` | ESP32 | BLE scan → `ble_beacon_seen` (enrolled only) |

Each project shares `main/puck_sign.{h,cpp}` (HMAC-SHA256 via mbedtls)
and mirrors the logic in `../pucks/src/puck_core/` — **keep them in sync**.

## Build (requires ESP-IDF)

```sh
cd sensors/firmware/puck_a   # or puck_b / puck_c
idf.py set-target esp32s3    # puck_a; esp32 for b/c
idf.py build flash monitor
```

## Provisioning (per unit, never committed)

- NVS namespace `puck`: `secret` (32-byte HMAC key, matches collector
  registry), puck_b adds `win_start`/`win_end` epoch-ms maintenance
  window, puck_c adds `enrolled` beacon key list, puck_a adds
  `known_bssids` inventory.
- Collector side: register each `device_id` with its secret via
  `Collector.register()` (see `../pucks/src/puck_core/collector.py`).

## Status

Skeletons implementing the real scan/debounce/filter loops and event
JSON, but **not compiled or flashed** — no ESP-IDF toolchain in this
environment and no hardware attached. Bring-up gate **H08** ("verify
each puck event and device identity") is pending physical devices.
Transport is `printf` over serial pending deployment wiring.
