# ACT subsystem — acceptance evidence index (#46)

Maps issue #46 "verify subsystem acceptance and engineering handoff"
criteria to merged + open work.

## Delivered

| Issue | PR | Package | Tests | Status |
|---|---|---|---|---|
| #33 Containment policy | #65 | `apps/containment/policy/` | 14 pytest | DONE logic — in-memory |
| #34 Lab executor | #66 | `apps/containment/executor/` | 9 pytest | PARTIAL — mock adapters |
| #35 Audit/recovery | #67 | `apps/containment/audit/` | 9 pytest | DONE logic — in-memory |
| #52 Closed loop | #78 (open) | `apps/glue/closed_loop/` | 9 pytest | PARTIAL — full chain simulated |

## Acceptance criteria status

- [x] Allowlisted actions — finite action types, target allowlist,
  TTL, HMAC fingerprint, separation of duties, replay/expiry/
  self-approval denials
- [x] Idempotent outbox — redelivery-safe, preserves queued on
  same-action redelivery
- [x] Independent verification — fake API-200 still FAILED; revert
  path; reachability re-probe
- [x] Audit — hash-chained append-only log, tamper detection,
  privileged recovery flow
- [x] Closed loop — approval→policy→outbox→executor→verify→chat;
  wrong-role/expired/replay/fingerprint denied; verify-fail→FAILED
- [x] Live approval→containment→verify path — `containment_executor.service`
  HTTP bridge wires gateway outbox webhook to executor+independent
  verify; 200 only on VERIFIED (17 pytest incl. live HTTP+auth round-trip)
- [ ] Real firewall/switch actuation — BLOCKED (no lab network gear)

## Reproduce tests

```sh
cd apps/containment/policy && PYTHONPATH=src python3 -m pytest tests/ -q    # 14
cd apps/containment/executor && PYTHONPATH=src python3 -m pytest tests/ -q  # 9
cd apps/containment/audit && PYTHONPATH=src python3 -m pytest tests/ -q     # 9
cd apps/glue/closed_loop && PYTHONPATH=src python3 -m pytest tests/ -q      # 9
```
