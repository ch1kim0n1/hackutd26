# UX subsystem — acceptance evidence index (#45)

Maps issue #45 "verify subsystem acceptance and engineering handoff"
criteria to merged + open work.

## Delivered

| Work | PR | Package | Tests | Status |
|---|---|---|---|---|
| Twin feed contract | #77 (open) | `apps/glue/twin_feed/` | 6 pytest | PARTIAL — data layer |
| Digital twin | #82 (open) | `apps/dashboard/twin/` | unverified | BLOCKED — no npm/live feed |
| RF intel | #83 (open) | `apps/dashboard/rf_intel/` | 6 pytest | PARTIAL — data layer only |
| Ops UX spec | #84 (open) | `apps/dashboard/ops_ux/` | 5 pytest | PARTIAL — contract only |

## Acceptance criteria status

- [x] Feed contract — provenance LIVE/REPLAY/SYNTHETIC enforced,
  scoped subscriptions, staleness flagged, no fabricated spectrum
- [x] Twin component — RoverMarker pose-from-telemetry only, STALE
  flag, IncidentMarker→incident+evidence, surveyed zones
- [x] RF intel — channel heatmap/BSSID/RSSI from real scans only,
  permission+scope-checked evidence
- [x] Ops composition — 6 regions, role visibility, ≤60s responder
  path, a11y requirements
- [ ] `npm install && npm run dev` verified — BLOCKED (no live feed)
- [ ] Live two-user UI demo — BLOCKED
- [ ] 60-second untrained-operator task test — BLOCKED (needs live UI)
- [ ] Screenshot/evidence artifacts — BLOCKED

## Reproduce tests

```sh
cd apps/glue/twin_feed && PYTHONPATH=src python3 -m pytest tests/ -q   # 6
cd apps/dashboard/rf_intel && PYTHONPATH=src python3 -m pytest tests/ -q # 6
cd apps/dashboard/ops_ux && python3 -m pytest test_ux.py -q              # 5
cd apps/dashboard/twin && npm install && npm run dev                     # needs feed
```
