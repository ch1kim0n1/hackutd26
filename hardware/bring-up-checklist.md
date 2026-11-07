# Bring-up Checklist — rover + pucks

Maps the H01–H10 gates from `docs/02-HARDWARE.md` to executable steps.
Every gate needs a dated, signed result in `test-evidence/` before the
corresponding production claim is made. **Nothing is "verified" until measured.**

| Gate | Test | Procedure | Pass condition | Evidence slot |
|---|---|---|---|---|
| H01 | Power rails | Multimeter on every rail with Pi disconnected: battery ~7.4 V, post-fuse motor rail, UBEC 6 V, D24V50F5 5 V, ESP32 3V3 | All within spec; no shorts; E-stop open = motor rail 0 V | `H01-power-rails.md` |
| H02 | Motor bench | Wheels raised; drive each motor channel fwd/rev at 25% then capped speed | Correct direction per side; no driver thermal shutdown; current logged | `H02-motor-bench.md` |
| H03 | E-stop energy cut | Drive motors; press E-stop | Motion stops < 200 ms; VM at drivers measures 0 V; re-enable requires explicit firmware clear + released button | `H03-estop.md` |
| H04 | Command watchdog | Drive at speed; unplug Pi↔ESP32 USB | Motors stop within command TTL (≤ 500 ms); fault telemetry on reconnect | `H04-watchdog.md` |
| H05 | Obstacle stop | Drive toward obstacle at capped speed | ToF override stops before contact; resume requires clear path + new command | `H05-obstacle.md` |
| H06 | Localization | Patrol route with AprilTag waypoints + encoders | Pose error within zone bounds; tag ID → waypoint mapping verified | `H06-localization.md` |
| H07 | Camera evidence | capture_photo at each zone | Image file + JSON sidecar (mission_id, zone, UTC, sha256) retrievable | `H07-camera.md` |
| H08 | Puck identity | Power each puck; collect 10 min | Events carry correct device_id, monotonic seq, HMAC valid, LED states match | `H08-pucks.md` |
| H09 | Patrol repeatability | Five full patrol_route runs | All complete collision-free; telemetry shows no fault states | `H09-patrols.md` |
| H10 | Pi brownout | Scope Pi 5 V rail during H09 runs | No brownout/reset; current peaks recorded | `H10-brownout.md` |

## Pre-energizing requirements (from wiring-diagram.md §6)

- [ ] BOM frozen: every `proposed` line confirmed purchased or substituted (update CSV status).
- [ ] Stall current measured per motor channel; motor fuse and driver rating confirmed adequate (conflict C-3).
- [ ] E-stop ordered in 1NO+1NC configuration; bench-tested before first drive.
- [ ] All pin maps re-verified against purchased board silkscreens (conflicts C-1, C-2, C-5).
- [ ] Firmware hashes recorded after flashing (`firmware-hashes.txt`).
- [ ] Measured current draw + estimated runtime recorded (`power-budget.md`).

## Safety rules during bring-up

- Wheels raised for ALL first-power and direction tests.
- One person at E-stop during any floor test.
- Never energize motor rail while probing logic pins.
- LiPo charging only in fire-safe area; storage at storage voltage when not testing.
