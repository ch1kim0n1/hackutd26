# Firmware host tests

The safety core (`rover_controller`, `rover_protocol`, `rover_json`,
`rover_types`) is pure C++17 and builds on any host with CMake + a C++17
compiler. `hal_espidf.cpp` / `main.cpp` are ESP-IDF-only and excluded here.

## Build & run

```sh
cd robotics/firmware/test
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build
./build/rover_tests     # unit tests, exits non-zero on failure
ctest --test-dir build  # same via ctest
./build/rover_sim       # scripted scenario -> JSON telemetry on stdout
```

## Coverage vs issue #11 acceptance

| Acceptance item | Test |
|---|---|
| Repeated E-stop | `test_estop` — press, release-latch, clear, re-press reject |
| Timeout on Pi disconnect | `test_watchdog` — TTL expiry stops motors, fault telemetry |
| Capped speed | `test_caps_and_ramp` — `speed_cap`/`rate_cap` rejections |
| Obstacle stop | `test_obstacle` — ToF threshold, hysteresis resume |
| Fault telemetry | `test_sensor_fault`, telemetry `fault` field everywhere |

`rover_sim` additionally demonstrates a full patrol → turn → obstacle →
estop → watchdog sequence as JSON telemetry for evidence review.

## What is NOT covered here

Physical flashing, real encoder/ToF/E-stop behavior, PWM output, and UART
transport require the ESP32 hardware and ESP-IDF toolchain
(`idf.py build flash`) — tracked by bring-up gates H02–H05 in
`hardware/bring-up-checklist.md`.
