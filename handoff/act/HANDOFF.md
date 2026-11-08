# ACT engineering handoff (#46)

## What exists

- `apps/containment/policy/` — finite action types, target allowlist,
  TTL, HMAC fingerprint (tamper-evident), separation of duties,
  replay/expiry/self-approval denials.
- `apps/containment/executor/` — idempotent outbox, lab-only adapter,
  independent verification, revert path.
- `apps/containment/audit/` — hash-chained append-only audit,
  privileged recovery, tamper detection.
- `apps/glue/closed_loop/` — full approval→containment→verify→chat
  orchestration (open PR #78).

## Integration touchpoints (docs/04 actions/approvals/audit_events)

- Proposals from agent (#20/#49) → policy consume → outbox worker →
  lab executor → independent verify → scope update (#26) → chat post
  (#27).
- External commands run through outbox worker — never DB transaction
  side effects.
- Audit chain covers every stage; recovery requires approve +
  independent verify.

## Known limitations / risks

- **All in-memory + mock adapters** — no real firewall/switch; lab
  executor adapters are fakes pending credentials/gear.
- Verification probes are injected callables — production needs real
  reachability/state checks.
- Fingerprint binds type+target+incident — params changes need policy
  review before widening.

## Next steps

1. Stand up lab network gear (owned test endpoints only).
2. Implement real executor adapters (switch ACL/port-isolate).
3. Wire outbox to SpacetimeDB `actions`/`approvals` tables.
4. Live demo: wrong-role/expired/replay denied → approved containment
   → verified → audit complete.
