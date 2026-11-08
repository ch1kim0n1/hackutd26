# AI subsystem — acceptance evidence index (#42)

Maps issue #42 "verify subsystem acceptance and engineering handoff"
criteria to merged work.

## Delivered (merged PRs)

| Issue | PR | Package | Tests | Status |
|---|---|---|---|---|
| #19 Nemotron client | #62 | `apps/agent/nemotron_client/` | 8 pytest | PARTIAL — client tested vs local HTTP, no live model |
| #20 Investigation agent | #63 | `apps/agent/investigator/` | 8 pytest | PARTIAL — scripted/fake model + tool registry |
| #21 Agent hardening | #64 | `apps/agent/hardening/` | 15 pytest | DONE logic — guards host-tested |
| #49 correlation→agent | #75 (open) | `apps/glue/correlation_agent/` | 6 pytest | PARTIAL — scripted driver |

## Acceptance criteria status

- [x] Pinned model/endpoint config — env-required, no defaults,
  `NVIDIA_API_KEY` mandatory
- [x] Bounded tool registry — 9 allowlisted tools w/ scope checks,
  budgets, evidence citations, proposal-only containment
- [x] Hardening — untrusted-text fencing, ToolGuard (authority
  denylist, budgets, loop detect), ModelOutputGuard (forbidden claims,
  fabricated citations), contradiction revision
- [x] Evidence-grounded reports — ≥3 tool calls, resolvable citations,
  mandatory unknowns + alternate explanation (#49)
- [ ] Real Nemotron inference — BLOCKED (no `NVIDIA_API_KEY`/endpoint)
- [ ] Live tool calls against SpacetimeDB backends — BLOCKED
- [ ] N01 "real tool calls" acceptance — needs live model + DB

## Reproduce tests

```sh
cd apps/agent/nemotron_client && PYTHONPATH=src python3 -m pytest tests/ -q  # 8
cd apps/agent/investigator && PYTHONPATH=src python3 -m pytest tests/ -q      # 8
cd apps/agent/hardening && PYTHONPATH=src python3 -m pytest tests/ -q         # 15
cd apps/glue/correlation_agent && PYTHONPATH=src python3 -m pytest tests/ -q  # 6
```
