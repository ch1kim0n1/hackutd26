# Test Evidence — hardware bring-up

This directory holds the measured proof required by `docs/02-HARDWARE.md`
("assembly photos, motor safety test report, firmware hashes, measured current
and run time"). **As of the BOM/wiring PR, no physical hardware has been
assembled or energized — every artifact below is a template awaiting real
measurements.** Do not mark gates passed without filling these in.

| Artifact | Gate | Status |
|---|---|---|
| `H01-power-rails.md` | Multimeter rail check, Pi disconnected | TEMPLATE |
| `H02-motor-bench.md` | Wheels-raised direction/speed test | TEMPLATE |
| `H03-estop.md` | E-stop removes motor energy | TEMPLATE |
| `H04-watchdog.md` | Pi-disconnect motor stop | TEMPLATE |
| `H05-obstacle.md` | ToF obstacle override | TEMPLATE |
| `H06-localization.md` | AprilTag + encoder calibration | TEMPLATE |
| `H07-camera.md` | Zone-labeled photo capture | TEMPLATE |
| `H08-pucks.md` | Puck event/identity verification | TEMPLATE |
| `H09-patrols.md` | Five collision-free patrols | TEMPLATE |
| `H10-brownout.md` | Pi rail under drive load | TEMPLATE |
| `power-budget.md` | Measured current + runtime | TEMPLATE |
| `firmware-hashes.txt` | SHA-256 of flashed binaries | PENDING flash |
| `photos/` | Assembly + wiring photos | PENDING assembly |

## Evidence rules

- Photos must show the actual build, not renderings; include the BOM line
  visible where possible.
- Multimeter/scope readings need date, operator, and instrument.
- Firmware hashes are `sha256sum` of the exact `.bin` flashed — regenerate on
  every firmware change.
- REPLAY or simulated results must be labeled as such and never satisfy a
  physical gate.
