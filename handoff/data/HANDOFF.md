# DATA engineering handoff (#41)

## What exists

- `docs/04-DATA-AND-INTERFACES.md` — authoritative schema + reducer
  contract (source of truth for all tables).
- `apps/glue/vertical_slice/` — in-memory pipeline proving collector →
  reducer → scoped subscriber semantics (PR #74, open).
- `apps/glue/twin_feed/` — unified feed contract consumed by UI
  (PR #77, open).

## Integration touchpoints

- Every subsystem writes through reducers: observations (devices),
  incidents (correlator/agent), actions/approvals (containment),
  scope_entries (IR), chat_messages (chat), audit_events (all).
- Clients get role+incident-scoped projections only — private source
  tables never leak cross-incident rows.
- Evidence artifacts stored separately; clients get short-lived
  authenticated URLs, never raw paths.

## Known limitations / risks

- **No SpacetimeDB deployment exists** — all "reducer" behavior is
  in-memory stand-ins; real module, permissions, and subscription
  auth are unbuilt.
- Version/nonce/idempotency semantics are specified + host-tested but
  not exercised against a real database.
- `observed_epoch` is a test convenience; production parses RFC3339.

## Next steps

1. Stand up SpacetimeDB (independent management host per docs/06).
2. Implement module: tables per docs/04 + reducers enforcing
   role/scope/version/lifecycle/bounds.
3. Port `vertical_slice` reducer semantics; re-run GLUE-01 live.
4. Wire subscriptions to `twin_feed`; verify private-table scoping.
