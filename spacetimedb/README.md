# SENTINEL HIVE — SpacetimeDB module

Authoritative transactional state + realtime projections for the command
center. Implements `docs/04-DATA-AND-INTERFACES.md` and the Winstead
compliance rules in `docs/06-WINSTEAD-COMPLIANCE.md`.

## Layout

- `src/schema.ts` — tables, enums, lists. All base tables are **private**;
  clients only ever see the public **views** in `src/views.ts`.
- `src/lib.ts` — shared guards: role checks, incident-scope checks, bounded
  string/JSON validation, audit writer, deterministic ID/canonical-JSON
  helpers, incident lifecycle transition table.
- `src/reducers-*.ts` — transactional reducers grouped by domain
  (ingest / alert / incident / mission / action / chat / admin).
- `src/views.ts` — role-scoped read projections (the only client-visible
  surface).
- `tests/smoke.ts` — end-to-end contract test (see below).

## Authorization model

- `ctx.sender` is the only trusted principal. Caller-supplied identity
  fields are never trusted.
- `users_and_roles` maps `Identity -> UserRole`
  (admin, commander, responder, observer, agent, device, executor, gateway).
  `bootstrapAdmin` is a one-time genesis reducer: it succeeds only while the
  directory is empty, so the first operator becomes admin; afterwards every
  role change requires an existing admin.
- `device_principals` binds a device `Identity` to exactly one `device_id`.
  A device principal may only ingest observations for its own device.
- `incident_access` grants per-incident levels (viewer / responder /
  commander). The incident creator is auto-granted commander.
- Every reducer enforces role + incident scope + lifecycle/expected-version
  rules and writes an `audit_events` row with before/after snapshots.

## Projections (cross-incident denial)

Base tables are private. Views filter server-side per `ctx.sender`:

- `incident_feed`, `chat_feed`, `scope_feed`, `evidence_feed`,
  `action_feed`, `approval_feed`, `incident_alert_feed`, `access_feed`
  return rows only for incidents the caller can access (admin: all;
  commander: commanded incidents; others: explicit grants).
- `pending_approvals` additionally requires commander-level access.
- `pending_missions` is gateway-only; `device_missions` shows a device
  principal only its own missions; `executor_outbox` is executor-only;
  `user_feed` is admin-only; `my_access` / `my_device_principal` are
  self-scoped.

A subscriber therefore never receives rows for incidents outside its scope —
cross-incident subscriptions are denied by construction, not by UI filtering.

## Failure / reconnect / authorization behavior

- **Replay & duplicates:** `observations.eventId` is unique — exact retries
  are idempotent no-ops; `seq <= devices.lastSeq` is rejected; chat
  `client_nonce` dedupes retries; action `fingerprint` dedupes re-proposals;
  mission result replays of terminal states are idempotent.
- **Bounded payloads:** all strings/JSON are length- and charset-checked;
  `data_json` <= 8 KiB, payloads <= 16 KiB; unknown kinds/enums rejected.
- **Freshness:** `observed_at` must be within (-24h, +skew] of server time.
- **Lifecycle:** incident transitions follow `INCIDENT_TRANSITIONS`
  (new→triage→investigating→containment_pending→contained→recovery→
  resolved→closed, plus dismissed); optimistic `version` checks reject
  stale writes.
- **Outbox:** approved actions enqueue `outbox` rows via the scheduled
  `maintenanceTick` reducer — external effects never happen inside a
  reducer transaction. Executors `claimOutbox` (pending→claimed) then
  `recordExecutorOutcome`; claims are restart-safe because state lives in
  the DB, not worker memory.
- **Reconnects:** subscriptions are server-authoritative; a reconnecting
  client re-receives the current view contents. Reducer calls are
  transactional — a dropped connection either commits fully or not at all,
  and idempotency keys make safe retries possible.
- **Authorization failures** surface as `SenderError` rejections; nothing
  is partially written (single transaction per reducer).

## Build / publish / test

```sh
cd spacetimedb
npm install
npm run typecheck     # tsc --noEmit over src/
npm run build         # spacetime build (wasm)
# local server must be running: spacetime start
spacetime publish sentinel-hive --server local --module-path . --yes
npm run generate      # client bindings -> bindings/ (gitignored)
npm run test:smoke    # regenerate bindings + run tests/smoke.ts
```

`tests/smoke.ts` spins up 7 independent identities (admin, device, gateway,
commander, responder, observer, executor), seeds the lab registry, and
asserts 27 behaviors: ingest dedupe/replay/forgery/oversize rejection,
scoped-view denial and grant, live chat fan-out to two subscribers, nonce
dedupe, RBAC negatives, action propose→approve(SoD)→outbox→executor→verify,
mission assign→dispatch, scope entries, and incident status transitions.
It persists per-role identity tokens in `.smoke-identity-tokens.json`
(gitignored) so repeated runs reuse stable principals; wipe with
`--delete-data=always` on publish for a clean slate.
