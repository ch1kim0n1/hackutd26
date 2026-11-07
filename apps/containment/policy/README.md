# Containment policy service (issue #33)

Approval-bound, allowlisted containment policy — `docs/04` action/
approval contracts, `docs/08` rules-for-contained-actions + threat 7
(race/retry on containment), role matrix.

## Guarantees

| Requirement | Enforcement |
|---|---|
| Scope-bound proposal | incident_id scope, finite `ActionType` enum (no freeform/shell), target must be in lab allowlist, reason ≥8 chars, TTL ≤900 s |
| Role checks | proposer ∈ {agent,responder,commander,admin}; approver ∈ {commander,admin} — server-side, not frontend claims |
| Separation of duties | `approver_id != proposer_id` — self-approval denied |
| Approval fingerprint | HMAC-SHA256 binds proposal_id + incident + action_type + target + proposer + TTL + created_at; `decide()` requires exact match — tampering any field invalidates |
| Replay protection | used fingerprints tracked; second decide on same proposal rejected by state machine |
| Expiry | proposals past TTL → `EXPIRED`, cannot be approved |
| Monotonic state | `mark_state()` with `allowed_from` guards executor transitions |

## Flow

```
agent/responder propose_containment
  -> ContainmentPolicy.propose()  [role+scope+target+TTL checks]
  -> proposal.fingerprint (HMAC, secret from deployment — dev default
     is explicitly NOT for production)
commander approve/deny
  -> ContainmentPolicy.decide()   [role, state, expiry, fingerprint,
                                   replay, separation-of-duties]
  -> approved_actions() for executor pickup (#34)
```

The agent (#20 `propose_containment`) and this service share the
proposal shape; wiring = bind agent backend to `propose()`.

## Tests

```sh
cd apps/containment/policy && PYTHONPATH=src python3 -m pytest tests/ -q
```

14 tests covering every deny path: bad propose role, wrong target,
bad enums, short reason, TTL bounds, incident scope, self-approval,
approver role, fingerprint mismatch/tamper, expiry, replay/duplicate,
deny path, guarded transitions, expiry-aware `approved_actions()`.

## NOT done

- In-memory store; production persistence is SpacetimeDB `actions`/
  `approvals` tables (docs/04) — same semantics, durable.
- `fingerprint_secret` dev default must be replaced by deployment
  secret management; fingerprints are HMAC not signatures — approver
  authN/Z is the identity layer's job (docs/08 trust boundary).
- No integration with #34 executor yet — `approved_actions()` +
  `mark_state()` is the contract it consumes.
