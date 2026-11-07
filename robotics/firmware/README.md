# Rover motor-controller firmware (ESP32)

ESP-IDF firmware for the rover's ESP32 motor controller: capped motion
primitives, quadrature-encoder odometry, VL53L1X ToF obstacle override,
command-TTL watchdog, physical E-stop handling, and JSON telemetry.
Safety contract: `docs/02-HARDWARE.md`, `docs/03-ROBOTICS-RF.md`; pin map:
`hardware/wiring-diagram.md` §3 (branch `hw/10-bom-wiring`).

## Layout

| Path | Contents |
|---|---|
| `main/rover_controller.*` | Safety core — pure C++17, host-testable |
| `main/rover_protocol.*` | UART line protocol (JSON commands/telemetry) |
| `main/rover_json.*` | Minimal JSON codec (no external deps) |
| `main/rover_types.*`, `rover_config.h` | States, faults, tuning constants |
| `main/hal_espidf.*`, `pins.h`, `main.cpp` | ESP-IDF HAL + app entry (target only) |
| `test/` | Host unit tests + scripted simulator |

## Serial protocol (Pi ↔ ESP32, 115200 8N1, JSON lines)

Commands (Pi → ESP32):

```json
{"v":1,"kind":"command","cmd_id":"c-1042","intent":"forward","speed_mmps":200,"ttl_ms":500}
{"v":1,"kind":"command","cmd_id":"c-1043","intent":"turn_left","rate_dps":45,"ttl_ms":500}
{"v":1,"kind":"command","cmd_id":"c-1044","intent":"stop"}
{"v":1,"kind":"command","cmd_id":"c-1045","intent":"zero_odometry"}
{"v":1,"kind":"command","cmd_id":"c-1046","intent":"estop_clear"}
{"v":1,"kind":"command","cmd_id":"c-1047","intent":"set_params","max_speed_mmps":200}
```

Intents: `forward`, `backward`, `turn_left`, `turn_right`, `stop`,
`zero_odometry`, `estop_clear`, `set_params`, `ping`.

Responses: `ack` (accepted + reason on reject) and `telemetry` at 10 Hz:

```json
{"v":1,"kind":"telemetry","seq":42,"uptime_ms":50120,"state":"driving",
 "v_left_mmps":200,"v_right_mmps":200,"odom_dist_mm":15230,
 "odom_heading_rad":0.0,"pose_x_mm":15230.0,"pose_y_mm":0.0,
 "dist_front_mm":412,"dist_rear_mm":388,"estop":false,"obstacle":false,
 "fault":"none","led":2}
```

## Safety behavior (enforced in `rover_controller.cpp`)

1. **E-stop** — polled every 20 ms tick. Active → motors zeroed, TB6612 STBY
   low, state `estopped`, fault `estop`. Latched after release until
   `estop_clear` command AND button released. Hardware NC contact additionally
   cuts motor-rail energy (wiring-diagram §1).
2. **Obstacle override** — front VL53L1X every tick, rear every 4th. Distance
   < `obstacle_stop_mm` (150) → immediate stop, `obstacle_hold` until both
   sensors read > `obstacle_resume_mm` (220). New motion commands rejected
   while held.
3. **Watchdog** — motion commands carry `ttl_ms` (50–5000, default 500).
   Expiry → motors stopped, fault `watchdog_timeout`. Covers Pi cable
   disconnect / hung mission runtime.
4. **Caps** — `speed_mmps` > `max_speed_mmps` (250 = 0.25 m/s mission cap)
   rejected `speed_cap`; turn `rate_dps` > `max_turn_rate_dps` rejected
   `rate_cap`; bad TTL rejected `ttl_range`. Rejection, never silent clamp.
5. **Ramp** — accel 400 mm/s², decel 1500 mm/s² per side.
6. **Sensor fault** — 5 consecutive ToF read failures → `sensor_fault`,
   motors disabled until cleared.

## Build

Target firmware (requires ESP-IDF + `vl53l1x` component):

```sh
cd robotics/firmware
idf.py set-target esp32
idf.py build flash monitor
```

Host tests (no ESP-IDF needed):

```sh
cd robotics/firmware/test
cmake -B build && cmake --build build
./build/rover_tests && ./build/rover_sim
```

## Calibration TODO (bring-up gates)

- `encoderMmPerCount` (default 0.05) and `mmpsPerDuty` (default 400 mm/s @
  100 %) — measure during H06/H02, update `rover_config.h` / `main.cpp`.
- `trackWidthMm` (160) — measure wheel separation.
- GPIO19/20 XSHUT availability — conflict C-1 in wiring-diagram; if absent,
  move rear ToF to Pi I2C and set `rearTofEnabled=false` path accordingly.

## Status

Host-tested logic complete; **not yet flashed or bench-tested** — physical
verification is gated by H02–H05 (see `hardware/bring-up-checklist.md`).
`hal_espidf.cpp` APIs follow ESP-IDF v5.x conventions but must be compile-
checked on first `idf.py build`.
