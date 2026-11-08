# OPS subsystem — acceptance evidence index (#47)

Maps issue #47 "verify subsystem acceptance and engineering handoff"
criteria to merged + open work.

## Delivered

| Work | PR | Package | Tests | Status |
|---|---|---|---|---|
| Chaos harness | #80 (open) | `apps/ops/chaos_harness/` | 5 pytest | PARTIAL — doubles, artifacts ready |
| Demo runner | #81 (open) | `apps/ops/demo/` | 4 pytest | PARTIAL — scripted transcript |
| docs/10 test plan | — | `docs/10-TEST-AND-DEMO.md` | n/a | DONE spec |

## Acceptance criteria status

- [x] Evidence runner records PASS/FAIL/NOT_RUN + artifacts —
  `chaos_harness.write_artifacts()` emits JSON+MD
- [x] 8 adversarial scenarios — replay, bad creds, lab compromise,
  private sub, chat injection, model injection, actuator verify
  fail, safety estop
- [x] Demo scripts — 90s full + 3min Winstead w/ explicit
  SIMULATED|LIVE mode (never mislabeled); rollback plan; submission
  checklist
- [ ] Three uninterrupted **live** demos — BLOCKED (needs deployed stack)
- [ ] Security/source proofs on live system — BLOCKED
- [ ] Deployment/release freeze — see #55

## Reproduce tests

```sh
cd apps/ops/chaos_harness && PYTHONPATH=src python3 -m pytest tests/ -q  # 5
cd apps/ops/demo && python3 -m pytest test_demo.py -q                    # 4
PYTHONPATH=src python3 -m chaos_harness --help 2>/dev/null; \
python3 -c "import sys; sys.path.insert(0,'apps/ops/chaos_harness/src'); \
from chaos_harness import ChaosHarness; ChaosHarness().write_artifacts('/tmp/chaos')"
```
