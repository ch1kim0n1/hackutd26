# Hardware — BOM, wiring, bring-up

Physical layer for SENTINEL HIVE: rover compute/motion/sensing, three sensor
pucks, and lab fixtures. Source of truth: `docs/02-HARDWARE.md`;
integration touchpoints: `docs/04-DATA-AND-INTERFACES.md` (canonical event +
mission contracts consumed by firmware/runtime code).

| File | Contents |
|---|---|
| `hardware-bom.csv` | Parts, quantities, procurement status, estimated cost |
| `wiring-diagram.md` | Pin-by-pin wiring for the proposed build + conflict log |
| `bring-up-checklist.md` | H01–H10 gate procedures mapped to evidence slots |
| `motor-safety-test-report.md` | Stall current / E-stop / thermal test template |
| `test-evidence/` | Measured proof artifacts (templates until hardware exists) |

## Current status — read before citing

- **BOM is a PROPOSED freeze candidate**, not purchased inventory. Every line
  is `proposed` until the team confirms physical availability (open decision
  in `docs/11-REFERENCES-AND-DECISIONS.md`). Costs are street-price estimates,
  not quotes.
- **No hardware has been assembled, energized, or tested.** All bring-up
  gates H01–H10 are NOT RUN. Wiring must be re-verified against purchased
  boards before first power (see conflict log in `wiring-diagram.md`).
- Firmware that consumes these pin maps lives in `robotics/firmware/` (rover
  ESP32) and `sensors/firmware/` (pucks); the Pi runtime lives in
  `robotics/rover/`.
