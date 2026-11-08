# Per-Device Bring-Up Checklist + Untested-Hardware Register

Issue #117. Companion to `bring-up-checklist.md` (H01–H10 safety gates) —
this document is the *per-device* procedure: power/cabling, firmware
flash, expected first telemetry, and rollback. **Every device below is
UNTESTED ON PHYSICAL HARDWARE** unless its register row says otherwise;
software/simulated paths are validated, hardware is not.

Register status vocabulary: `SIM-VERIFIED` (fake/sim contract tests pass),
`FW-REVIEWED` (firmware builds/host-tests pass, never flashed),
`UNTESTED-HARDWARE` (no physical verification performed or claimed).

## 1. Rover compute — Raspberry Pi 5

- **Power/cables:** 5 V/5 A PD supply or UBEC from battery; micro-HDMI/
  USB-C console; UART to ESP32 per `wiring-diagram.md` §3; E-stop NC loop
  in series with motor rail enable (H01/H03).
- **Firmware flash:** host OS image + `rover-mission` package
  (`pip install -e robotics/rover[mqtt,serial,camera]`); ESP32 flashed
  separately (see §2). Record image hash in `test-evidence/`.
- **Expected first telemetry:** `rover_mission` service connects to ESP32
  (`/dev/ttyAMA0` or USB), emits `device_health`/`mission_status`
  observations with `pose_confidence` and monotonic `seq` on
  `sentinel/v1/rover-01/telemetry` (HMAC-signed if key provisioned).
- **Rollback:** re-image SD card from golden image; ESP32 rollback in §2.
- **Status:** `SIM-VERIFIED` service/missions; `UNTESTED-HARDWARE` boot,
  UART, power budget (H10).

## 2. ESP32 motor controller

- **Power/cables:** 3V3 logic, motor rail via fuse + E-stop (H01); ToF
  VL53L1X on I2C; encoder quadrature inputs; driver enables per
  `wiring-diagram.md` §3.
- **Firmware flash:** ESP-IDF project `robotics/firmware/` —
  `idf.py set-target esp32 && idf.py build flash`; host tests
  (`cd robotics/firmware/test`) must pass first; record `firmware-hashes.txt`.
- **Expected first telemetry:** JSON-lines telemetry @115200 8N1:
  odom pose, wheel velocities, `dist_front_mm`, `estop`, `obstacle`,
  `fault`; command TTL watchdog stops motion ≤ 500 ms on link loss (H04).
- **Rollback:** reflash previous known-good partition; keep
  `sdkconfig.defaults` pinned; motors stay disabled until explicit enable.
- **Status:** `FW-REVIEWED` (host unit tests + simulator exist);
  `UNTESTED-HARDWARE` all H02–H05 gates.

## 3. LiDAR — Garmin Lidar-Lite / MS200

- **Power/cables:** 5 V supply, UART/serial or PWM per `autonomy/config.yaml`
  `lidar.mode` (`serial` port/baud or `pipe`); mount offset + rotation
  direction configured.
- **Firmware flash:** none (COTS); verify cable order against silkscreen.
- **Expected first telemetry:** distance frames consumed by
  `autonomy/lidar.py` (`PipeLidar`/`SerialLidar`); scan-match quality
  visible in `autonomy` run summary (`pose_error_m`).
- **Rollback:** power-cycle; fall back to `sim.py` world scans — autonomy
  loop holds still on missing scans (safe default).
- **Status:** `UNTESTED-HARDWARE` (serial/PWM paths unexercised;
  `autonomy --sim` verified).

## 4. Camera — rover CSI/USB

- **Power/cables:** CSI ribbon or USB3; IR-filter considerations for
  AprilTag detection at zone waypoints.
- **Firmware flash:** none; `opencv-python` on Pi (`[camera]` extra).
- **Expected first telemetry:** `capture_photo` missions produce image +
  JSON sidecar (mission_id, zone, UTC, sha256) — H07.
- **Rollback:** `Cv2Camera` raises explicit `RuntimeError` on open/capture
  failure; mission records `reason` and continues (no crash).
- **Status:** `SIM-VERIFIED` (`SyntheticCamera` contract); `UNTESTED-HARDWARE`
  real capture, focus, low-light.

## 5. Pucks A/B/C — ESP32-S3 sensor nodes

- **Power/cables:** USB-C 5 V each; Wi-Fi join `sentinel` SSID; LED/buzzer
  per `sensors/firmware/puck_*`.
- **Firmware flash:** `sensors/firmware/puck_a|puck_b|puck_c` (ESP-IDF or
  Arduino per README); enroll device principal + MQTT password via
  `deploy/scripts/bootstrap.sh` + `deploy/seeds/seed.ts`.
- **Expected first telemetry:** signed `Observation`s on
  `sentinel/v1/<device>/telemetry` (HMAC), monotonic `seq`, correct
  `device_id` — H08. `puck_core` `ConsoleTransport`/`MqttTransport`
  contract-tested.
- **Rollback:** reflash prior firmware; revoke principal in SpacetimeDB
  (`revokeDevicePrincipal`) to cut ingest instantly.
- **Status:** `SIM-VERIFIED` (collector/auth/transport contract tests);
  `UNTESTED-HARDWARE` RF scans, HMAC on-device, LED states.

## 6. Kismet / Wi-Fi monitor

- **Power/cables:** USB Wi-Fi adapter supporting monitor mode; host =
  correlator host or dedicated Pi.
- **Firmware flash:** none; `kismet` package + channel-hop config in
  `sensors/sdr|correlator` config dirs.
- **Expected first telemetry:** `dot11.*` JSON-lines →
  `correlator.adapters.adapt_kismet_record` → `wifi_ap_seen`/`wifi_probe`
  observations (already-captured authorized data only).
- **Rollback:** stop kismet; correlator dedupe/inventory unaffected.
- **Status:** `SIM-VERIFIED` adapter parsing on fixtures;
  `UNTESTED-HARDWARE` monitor-mode capture rates, regulatory domain.

## 7. Network wand — Pi Zero 2 W + Archer T4U Plus

- **Power/cables:** Pi Zero 5 V; Archer T4U on USB (`wlan1` monitor mode
  via `monmode.sh`); SSD1306 OLED + NeoPixel + buzzer + buttons per
  `network_wand_code/`.
- **Firmware flash:** host image + `pip install -r requirements.txt`;
  `sentinel-wand.service` for autostart.
- **Expected first telemetry:** POST `/api/wand` reports every
  `poll_seconds` — **contract frozen in `backend_contract.py`
  (`WandReport`/`WandCommand`/`FakeWandBackend`); production
  `backend/app.py` is NOT implemented — see register R-4.**
- **Rollback:** `--no-hw` console mode; disable service; wand degrades to
  local buttons only (backend optional by design).
- **Status:** `SIM-VERIFIED` contract tests (7); `UNTESTED-HARDWARE`
  monitor mode, OLED, buttons, real RSSI.

## 8. Honeypot host

- **Power/cables:** any Linux host with monitor-capable Wi-Fi (or the
  rover Pi as `ap` mode via hostapd config emitted by
  `rover_mission/honeypot.py`).
- **Firmware flash:** none; decoy SSID list in code/config.
- **Expected first telemetry:** rogue probe/auth frames →
  `ble_beacon`/`wifi_probe`-class hostile observations + incident
  correlation (defensive lab scope only — no jamming/interference).
- **Rollback:** stop beacon injection / hostapd; decoys disappear.
- **Status:** `SIM-VERIFIED` (`Honeypot` tracker unit-tested);
  `UNTESTED-HARDWARE` scapy injection, hostapd path, range.

## Untested-hardware register

| # | Item | Boundary | Status | Needed to verify |
|---|---|---|---|---|
| R-1 | ESP32 UART protocol end-to-end | rover pose/commands | `FW-REVIEWED` | Physical Pi↔ESP32 link, H02–H05 |
| R-2 | AprilTag detection on real camera | localization | `SIM-VERIFIED` fake | Camera + tags, H06 |
| R-3 | LiDAR serial/PWM ingest | autonomy mapping | `UNTESTED-HARDWARE` | MS200/Lidar-Lite on Pi |
| R-4 | `POST /api/wand` production backend | wand backend | **MISSING impl** | `backend/app.py` (Team B/future) |
| R-5 | On-device HMAC signing (pucks/rover) | telemetry auth | `SIM-VERIFIED` verify-side | Flash + key provisioning per device |
| R-6 | Kismet monitor-mode capture | RF ingest | `SIM-VERIFIED` parse | Adapter + regulatory domain |
| R-7 | Honeypot RF injection/AP mode | hostile detection | `SIM-VERIFIED` logic | Monitor NIC / hostapd host |
| R-8 | Power budget & brownout | whole rover | `UNTESTED-HARDWARE` | H01, H10 metering |
| R-9 | E-stop energy cut timing | motor safety | `UNTESTED-HARDWARE` | H03 (<200 ms) measurement |
| R-10 | Command watchdog TTL | motor safety | `FW-REVIEWED` | H04 link-cut test |

**Rule:** no document, dashboard label, or PR may claim hardware
verification for any row above. `SIM`/`DEMO` provenance must remain on
all simulated telemetry.
