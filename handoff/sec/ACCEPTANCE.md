# SEC subsystem — acceptance evidence index (#43)

Maps issue #43 "verify subsystem acceptance and engineering handoff"
criteria to merged work.

## Delivered (merged PRs)

| Issue | PR | Package | Tests | Status |
|---|---|---|---|---|
| #22 Control plane | #68 | `apps/control_plane/` | 9 pytest → W01a–e | PARTIAL — policy layer, no physical net |
| #23 Identities/RBAC | #69 | `apps/identity/` | 7 pytest → W02a–e | PARTIAL — in-memory, no real IdP |
| #24 Threat tests | #70 | `apps/security_tests/` | 6 pytest + 6/6 run | PARTIAL — doubles, not deployed infra |
| #79 acceptance | #79 (open) | `apps/glue/acceptance/` | 4 pytest | PARTIAL — SIMULATED mode |

## Acceptance criteria status

- [x] Default-deny access matrix — lab segment reaches nothing;
  token-gated services; containment needs server-side approval
  fingerprint-bound to action
- [x] RBAC — admin/commander/responder/observer + machine principals;
  per-incident scope; human-only login; immediate revocation; all
  decisions audited
- [x] Relay — outbound-only, HMAC, dedup, seq monotonic, rate/size
  limits, fail-closed on identity/policy/audit outage
- [x] Six boundary checks — network deny, forgery, subscription enum,
  expired sessions, evidence upload, identity boundary → PASS/FAIL
  evidence artifacts
- [ ] Physical VLAN/firewall/mTLS isolation — BLOCKED
- [ ] Independent OIDC IdP deployment — BLOCKED
- [ ] W01/W02 recorded PASS on real infra — BLOCKED

## Reproduce tests

```sh
cd apps/control_plane && PYTHONPATH=src python3 -m pytest tests/ -q    # 9
cd apps/identity && PYTHONPATH=src python3 -m pytest tests/ -q          # 7
cd apps/security_tests && PYTHONPATH=src python3 -m pytest tests/ -q    # 6
PYTHONPATH=src python3 -m threat_tests --out report                     # 6/6 PASS
```
