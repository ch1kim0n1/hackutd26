# HW subsystem — acceptance evidence index (#39)

Maps issue #39 "verify subsystem acceptance and engineering handoff"
criteria to merged work. Statuses: DONE (tested), PARTIAL (host-tested,
physical pending), BLOCKED (needs hardware/site).

## Delivered (merged PRs)

| Issue | PR | Package | Tests | Status |
|---|---|---|---|---|
| #10 BOM/wiring | #56 | `hardware/` | CSV validated (39 items, ~$546) | DONE docs; measurements/photos BLOCKED |
| #11 Rover firmware | #57 | `robotics/firmware/` | 71 host checks, 0 failures | PARTIAL — host core only, no ESP32 flash |
| #12 Mission runtime | #58 | `robotics/rover/` | 28 pytest + 5 sim patrols | PARTIAL — sim nav, no real Pi/ESP32 |

## Acceptance criteria status

- [x] Interfaces match `docs/04-DATA-AND-INTERFACES.md` — mission
  protocol, telemetry, evidence artifact schema implemented
- [x] Failure/permissions/reconnect exercised — HMAC mission auth,
  E-stop latch, watchdog, obstacle override, stale-telemetry flags
  all host-tested
- [x] Logs/test evidence committed — pytest suites in each package
- [ ] Real end-to-end data/event flow on hardware — BLOCKED (no ESP32,
  Pi, motors, encoders, camera in this environment)
- [ ] Bring-up gates H01–H10 + H08 motor safety — BLOCKED, requires
  physical assembly per `hardware/BRING-UP-CHECKLIST.md`
- [ ] Joint review by subsystem owners — pending team review

## Reproduce tests

```sh
cd robotics/firmware && ./build_host.sh && ./run_tests   # 71 checks
cd robotics/rover && PYTHONPATH=src python3 -m pytest tests/ -q
python3 -m rover_mission.cli --simulate                  # 5 patrols
```
