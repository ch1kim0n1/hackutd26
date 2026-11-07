# UX-28 React/R3F live 3D office digital twin (#28)

Source of truth: `docs/07-COMMAND-CENTER.md`; data contract:
`apps/glue/twin_feed` (GLUE-04, PR #77) — `FeedItem{kind, ref_id, at,
provenance, payload, stale}`.

## Files

- `package.json` — React 18 + three + @react-three/fiber + drei + vite
- `src/Twin.jsx` — Canvas scene: `RoverMarker` (pose from `rover_pose`
  telemetry only, STALE flag dims+labels), `IncidentMarker` (click →
  `onSelectIncident` links incident + evidence), `ZoneAssets` wireframe
  surveyed zones, 1s poll of `feed.stream(sub_id)`.

## Contracts honored

- Rover pose derives **only** from telemetry — never fabricated.
- `stale` items render amber + "STALE" label.
- Incident markers carry `incident_id` + evidence ref for drilldown.
- Subscription auth: `feed.subscribe(principal)` server-side; role/
  scope never client-claimed.
- No spectrum rendering — RF evidence is #29's drilldown panel.

## NOT verified — needs npm install + live feed

- `npm install && npm run dev` requires network + the live
  `TwinFeed`/SpacetimeDB subscription backend (unmerged #51).
- No screenshot possible here; acceptance (pose-from-telemetry,
  stale flag, alert→incident+evidence link) verified by code review
  against the feed contract, pending live demo.
- `currentUser()` is a placeholder — wire to session principal.
