# Response audit + recovery (issue #35)

Auditable response timeline and safe recovery/re-enable flow —
`docs/04` audit_events contract, `docs/08` evidence provenance +
contained-action rules.

## Audit log (`audit.py`)

Append-only, **hash-chained** JSONL log:

- Every entry: seq, event_id, UTC `at`, actor + role, operation
  (`propose|approve|deny|execute|verify|recover_*|note`), entity,
  incident_id, reason, before/after state, verification result,
  trace_id, `prev_hash`, `hash`.
- `verify()` recomputes the whole chain — any historical edit breaks
  it (tamper-evident exports). Documented caveat (docs/08): chaining
  flags edits but does not make a compromised DB immutable.
- `timeline()`/`operations_for()` scoped queries by incident, entity,
  actor — distinguishes proposal/approval/execution/verification as
  separate operations.
- Optional JSONL persistence with reload.

## Recovery (`recovery.py`)

Re-enable is itself privileged — same rigor as containment:

1. `propose()` — recovery request (reason ≥8 chars), audited
2. `approve()` — commander/admin only, **no self-approval**, audited
   approve/deny
3. `execute()` — `revert_fn` (executor revert path) then INDEPENDENT
   `verify_fn` probe; `RECOVERED` only when probe confirms restoration;
   API success without verified restore → `RECOVERY_FAILED`
4. Every stage emits audit entries incl. verification results —
   rollback for the test lab = the executor's `revert()` path (#34)

## Tests

```sh
cd apps/containment/audit && PYTHONPATH=src python3 -m pytest tests/ -q
```

9 tests: lifecycle operation distinction, tamper detection, JSONL
persistence/reload, actor/entity filters, recovery requires approval,
wrong-role + self-approval denied, full revert+verify flow, verify-
failure → RECOVERY_FAILED (not silent success), chain integrity.

## Integration (docs/04)

- `AuditLog` maps to `audit_events` table (actor, operation, entity,
  before/after hash, at, trace_id); hash chain = `before_hash`/
  `after_hash` semantics made explicit.
- Recovery binds #33 policy (approval semantics) + #34 executor
  (`revert`/`verify`) — `revert_fn`/`verify_fn` are the injection
  points.

## NOT done

- In-memory + optional JSONL; production = SpacetimeDB `audit_events`
  + evidence store.
- `verify_fn`/`revert_fn` are callables — real bindings are the #34
  adapters on lab hardware.
- Retention/export signing (signed snapshots) is deployment work.
