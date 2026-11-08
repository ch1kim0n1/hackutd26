# DATA subsystem — acceptance evidence index (#41)

Maps issue #41 "verify subsystem acceptance and engineering handoff"
criteria to merged + open work.

## Delivered

| Work | PR | Package | Tests | Status |
|---|---|---|---|---|
| docs/04 contracts | — | `docs/04-DATA-AND-INTERFACES.md` | n/a | DONE spec |
| Vertical slice | #74 (open) | `apps/glue/vertical_slice/` | 7 pytest | PARTIAL — in-memory reducer |
| Twin feed | #77 (open) | `apps/glue/twin_feed/` | 6 pytest | PARTIAL — feed contract only |
| SpacetimeDB deployment | — | — | — | BLOCKED — no live DB here |

## Acceptance criteria status

- [x] `docs/04` table contracts defined — devices/zones/assets/
  observations/alerts/incidents/evidence/missions/scope_entries/
  actions/approvals/users_and_roles/chat_messages/audit_events/
  rf_frames/health
- [x] Reducer semantics specified — role+incident scope, expected
  version, actor identity, lifecycle, bounded payload, idempotency
  nonces, private-table projections
- [x] Live SpacetimeDB module deployed — `spacetimedb/` (v2.14.1),
  20 private tables, ~30 reducers, role-scoped views
- [x] Live reducers verified — `spacetimedb/tests/smoke.ts` **44/44**
  on local `sentinel-hive` (authz, dedupe, correlation, SoD approvals,
  outbox→verify, mission lifecycle incl. mission_status ingest)
- [x] Two authorized live subscribers — dual-client live chat/projection
  fan-out exercised in smoke (commander+responder scoped views)
- [x] Private-table leak tests — scoped view denial verified pre/post
  `grantIncidentAccess` in smoke; observers cannot see unscoped incidents
- [x] Vertical slice proves pipeline shape — auth collector →
  normalized obs → dedup → scoped fan-out (7 pytest)
- [ ] Physical hardware acceptance — human-required (see #39 gate)

## Reproduce tests

```sh
cd spacetimedb && npm run test:smoke                                    # 44 live checks
cd apps/glue/vertical_slice && PYTHONPATH=src python3 -m pytest tests/ -q  # 7
cd apps/glue/twin_feed && PYTHONPATH=src python3 -m pytest tests/ -q        # 6
cd services/gateway && npx tsx test/validate.test.ts                     # 17
```

## Handoff note

The canonical contract is `docs/04-DATA-AND-INTERFACES.md`. The live
module `spacetimedb/` implements it; `services/gateway` + `deploy/` wire
the authenticated MQTT→ingest path and the seeded demo deployment.
GLUE spec packages (`apps/glue/*`) model flows and are not yet bound to
the live views — that binding is follow-on work, not a blocker for the
DATA gate's software evidence.
