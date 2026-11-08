# UX engineering handoff (#45)

## What exists

- `apps/glue/twin_feed/` — unified feed contract (poses/RF/photos/
  timeline/scope/chat; provenance+scope+staleness).
- `apps/dashboard/twin/` — React/R3F scene scaffold consuming the feed.
- `apps/dashboard/rf_intel/` — RF channel/BSSID/RSSI data layer +
  permission-checked evidence drilldown.
- `apps/dashboard/ops_ux/` — layout/a11y/role-visibility contract +
  ≤60s responder task path.

## Integration touchpoints (docs/07)

- Twin/RF/ops UI all consume `twin_feed` + SpacetimeDB subscriptions —
  auth server-side, projections role+incident scoped.
- Evidence artifacts fetched via short-lived authenticated URLs only.
- Chat/incident/scope panels bind to #25–27 services.

## Known limitations / risks

- **No live frontend verified** — twin scaffold never built/run;
  `currentUser()` placeholder pending session wiring.
- Data layers are Python contracts — React bindings are thin and
  untested against real subscription streams.
- A11y contract is a checklist, not verified UI behavior.
- No screenshots/evidence artifacts possible without running stack.

## Next steps

1. `npm install` in `apps/dashboard/twin`; wire `feed` to live
   SpacetimeDB subscriptions + session principal.
2. Build RF drilldown panel on `rf_intel` data layer.
3. Compose ops layout per `ops_ux` spec; implement a11y checklist.
4. Run ≤60s responder task test + capture screenshot evidence.
