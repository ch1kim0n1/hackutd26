# OPS-38 deterministic stage demo + rollback + submission (#38)

## Demo scripts (`demo.py`)

- `FULL_DEMO_90S` — 7 beats / ~90s: login → CORR01 correlation →
  Nemotron investigation → commander approval → verified containment →
  team update → packet export.
- `WINSTEAD_3M` — adds W01/W02/W05 adversarial beats (lab pivot denied,
  mid-demo revoke, cross-incident denial, replay drop).

```sh
python3 -c "import sys; sys.path.insert(0,'apps/ops/demo'); \
from demo import *; import json; \
print(json.dumps(run_demo(FULL_DEMO_90S), indent=2))"
```

Every step carries `mode: SIMULATED|LIVE` — replay output is **never**
labeled live. `write_transcript()` emits JSON artifact.

## Stage checklist

1. Pre-flight: all services healthy, lab link state known, backups current.
2. Run demo; record screen + `demo_transcript.json`.
3. If any step fails: invoke rollback (below), mark NOT RUN — never fake.

## Rollback plan

- **Containment rollback**: revert approved action via executor revert
  path (#34/#35 audit-recovery), re-verify independently, post system
  message.
- **Software rollback**: redeploy previous tagged release; SpacetimeDB
  snapshot restore for table state.
- **Demo abort**: safe shutdown = disable actuator power, preserve
  evidence store read-only, snapshot audit log.

## Submission artifacts

- `demo_transcript.json` per run (3 uninterrupted demos required)
- chaos_report.json/.md from #37 harness
- W01–W05 recorded results (only REAL-mode counts)
- This file + `docs/10-TEST-AND-DEMO.md` checklist

## NOT done

- Transcript is scripted/simulated — the 3 uninterrupted **live** demos
  require deployed hardware+stack; cannot be produced here.
- No real screen recording possible; JSON transcript is the artifact.
