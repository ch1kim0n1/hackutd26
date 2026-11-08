# HW engineering handoff (#39)

## What exists

- `hardware/` — BOM (`bom.csv`, 39 line items), wiring diagram,
  bring-up checklist, motor safety report, test-report template.
- `robotics/firmware/` — ESP-IDF project; host-testable C++ core:
  E-stop latch, watchdog, obstacle override, speed caps, encoder odom,
  JSON protocol. ESP-IDF HAL layer thin over the core.
- `robotics/rover/` — Pi-side Python mission service: HMAC mission
  auth, local rejection, surveyed routes, nav, AprilTag hooks,
  SHA-256 evidence artifacts, telemetry.

## Integration touchpoints (docs/04)

- Rover telemetry → collector relay → `devices`/`observations` tables.
- Mission commands flow control-plane → gateway → rover (never direct
  browser→device).
- Evidence artifacts → protected store → `evidence` refs w/ hashes.

## Known limitations / risks

- **No physical hardware was available** — firmware is host-tested
  skeleton; real ESP-IDF build, pin mux, motor driver bring-up, and
  AprilTag camera pipeline are unverified on silicon.
- Route coordinates, BOM part numbers, pin map are placeholders pending
  real survey/procurement.
- Simulated patrols prove mission logic, not physical safety — E-stop
  must be bench-verified before any powered motion.

## Next steps for receiving team

1. Procure BOM; assemble per `hardware/wiring-diagram.md`.
2. Flash firmware; run `hardware/BRING-UP-CHECKLIST.md` H01–H10.
3. Survey office; replace placeholder routes in
   `robotics/rover/routes/`.
4. Record H08 motor safety report + test-report template evidence.
