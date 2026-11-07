# Sensor pucks (issue #13)

Three independent ESP32 pucks emit canonical observations per
`docs/04-DATA-AND-INTERFACES.md`. Source of truth: `docs/03-ROBOTICS-RF.md`.

| Puck | Hardware | Role | Event kinds |
|---|---|---|---|
| A | ESP32-S3 | 2.4 GHz Wi-Fi scan (SSID/BSSID/channel/RSSI) | `wifi_ap_seen` |
| B | ESP32 + reed switch | cabinet open/close, debounced | `cabinet_contact_open/closed` |
| C | ESP32 | BLE observe, enrolled beacons only | `ble_beacon_seen` |

All pucks also emit `device_health`; the collector synthesizes
`device_offline` — pucks never claim liveness they don't have.

## Layout

- `pucks/src/puck_core/` — host-testable Python core mirroring the firmware:
  `models.py` (canonical event), `auth.py` (HMAC-SHA256),
  `inventory.py` (known BSSIDs / enrolled beacons / maintenance windows),
  `puck_a.py`, `puck_b.py`, `puck_c.py`, `collector.py` (authenticated ingest
  + staleness), `puck_base.py`.
- `pucks/tests/test_pucks.py` — 13 tests (auth, debounce, dedup, enrollment
  filtering, collector rejects, stale/offline).
- `firmware/puck_{a,b,c}/` — ESP-IDF projects (ESP32-S3 for A, ESP32 for B/C).
  **Skeletons: logic mirrors the Python core but is NOT hardware-validated —
  bring-up gate H08 pending.**
- `pucks/config/inventory.example.json` — authorized-fixture template.

## Authentication & trust

- Each puck holds a per-device 32-byte HMAC secret (NVS/efuse on device,
  `PUCK_DEVICE_SECRET` env for host runs). Never committed.
- Events are signed over the canonical JSON (sorted keys, compact) — same
  scheme as rover missions.
- `Collector.ingest` enforces, in order: packet size, schema version,
  known device, zone match, kind-vs-device-type, signature, strictly
  increasing `seq` (replay/stale rejection). Rejections are logged with
  reason, never trusted.
- The collector adds `received_at` server-side; device `observed_at` is
  evidence, not authority.

## Known/unknown semantics

- Puck A flags `known_bssid`, `ssid_known`, `unknown_bssid_streak`,
  `suspicion` ∈ {none, first_unknown_bssid, unknown_bssid_on_known_ssid}.
  Streak ≥ 2 feeds RF01 downstream — suspicion, **not proof** of evil twin.
- Puck B sets `authorized=true` on open ONLY inside a maintenance window
  for its zone; closes are always `authorized=true`. PHY01 consumes
  open-with-authorized=false.
- Puck C emits only enrolled beacon keys (address or service UUID);
  everything else is counted (`dropped_unenrolled`) and discarded — no
  people tracking, no BLE fingerprint retention.

## Failure / reconnect / authorization behavior

- **Wi-Fi/BLE scan failure:** firmware logs and retries next interval;
  host core surfaces `device_health` degraded events via
  `PuckBase.health_event()`.
- **Serial/MQTT link loss:** collector marks device `stale` after
  `stale_after_s` (default 30 s) and `offline` after 4×; `refresh_health()`
  emits collector-synthesized `device_offline` events so dashboards see
  the gap — absence of events is never silently "all clear".
- **Reconnect:** `seq` is monotonic per device and survives reboots only if
  persisted (TODO hardware: store seq high-water mark in NVS to prevent
  post-reboot replay ambiguity — collector rejects seq regression anyway).
- **Authorization:** inventory is provisioned, not learned over RF. A new
  "known" BSSID or beacon requires an operator inventory update — devices
  cannot self-enroll.
- **Revocation:** removing a device from the collector registry makes its
  events `unknown_device` rejects; rotating `PUCK_DEVICE_SECRET` invalidates
  old signatures immediately.

## LED states (`PuckBase.led_state`)

`ok → solid_green`, `degraded/stale → blink_amber`, `offline → off`.
Puck B additionally lights LED while cabinet is open (physical visibility).

## Integration touchpoints (docs/04)

- Events → collector → `ingestObservation` reducer → `observations` table.
- `wifi_ap_seen` feeds RF01; `cabinet_contact_open` feeds PHY01;
  CORR01 joins both within 120 s same zone (issue #14).
- `device_offline`/`device_health` → `devices.status`/`health` tables.

## Tests

```sh
cd sensors/pucks && PYTHONPATH=src python3 -m pytest tests/ -q   # 13 passed
```

Covers: signature round-trip + tamper, known/unknown BSSID + streak
suspicion, scan dedup, monotonic seq, reed debounce bounce rejection,
maintenance-window authorized/unauthorized open, enrolled-only BLE +
dedup, collector accept + forgery/replay/kind/zone/unknown-device rejects,
stale→offline transitions.

## NOT done — needs hardware

- ESP-IDF builds unverified (no ESP-IDF toolchain here); firmware marked
  H08-pending throughout.
- Real Wi-Fi scan results, reed GPIO, BLE radios, NVS provisioning,
  per-unit secrets, LED wiring.
- Transport from device to collector (serial→gateway or MQTT) is
  stubbed as `printf` in firmware; pick up in deployment issue.
