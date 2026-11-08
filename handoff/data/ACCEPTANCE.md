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
- [x] Vertical slice proves pipeline shape — auth collector →
  normalized obs → dedup → scoped fan-out (7 pytest)
- [ ] Live SpacetimeDB module + reducers deployed — BLOCKED
- [ ] Two authorized live subscribers on real DB — BLOCKED
- [ ] Private-table leak tests on real deployment — BLOCKED

## Reproduce tests

```sh
cd apps/glue/vertical_slice && PYTHONPATH=src python3 -m pytest tests/ -q  # 7
cd apps/glue/twin_feed && PYTHONPATH=src python3 -m pytest tests/ -q        # 6
```

## Handoff note

The canonical contract is `docs/04-DATA-AND-INTERFACES.md`. All
subsystem packages implement against it; the SpacetimeDB module is
the remaining build — schema DDL + reducer functions per the contract,
then re-run GLUE-01 (#48) against the live DB.
