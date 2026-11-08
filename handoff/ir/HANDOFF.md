# IR engineering handoff (#44)

## What exists

- `apps/incident_records/` — Incident model + 9-state machine,
  optimistic-concurrency updates, timeline, evidence links,
  packet export.
- `apps/scope_matrix/` — per-CIA scope entries, evidence-gated status
  transitions, impact estimates, immutable snapshots, audit.
- `apps/incident_chat/` — incident rooms + command channel, server-side
  membership/roles, nonce dedup, presence/unread, system posts,
  sanitization.

## Integration touchpoints (docs/06 R03–R05, docs/04)

- `incidents`/`evidence`/`audit_events`/`scope_entries`/`chat_messages`
  tables — reducers must call `IdentityService.authorize()` +
  version checks server-side.
- Chat system posts link action/evidence ids from #52 closed loop.
- Scope evidence kinds map to real artifact types at integration.
- Export packets feed #38 submission artifacts.

## Known limitations / risks

- **All in-memory** — production = SpacetimeDB tables + reducers;
  conflict/chat semantics proven at service layer only.
- No offline message delivery claimed; presence is service-level
  (needs websocket heartbeat).
- Evidence-kind taxonomy (STRONG/WEAK) is ours — validate against real
  artifact types during integration.
- Sanitization strips tags; renderers must still escape output.

## Next steps

1. Port to SpacetimeDB `incidents`/`scope_entries`/`chat_messages`
   reducers preserving version/conflict/nonce semantics.
2. Wire chat subscriptions + presence heartbeats.
3. Two-browser demo: concurrent edit conflict, live chat, scope
   updates, reconnect history.
4. Map evidence kinds to real artifact taxonomy; run W03–W05 REAL.
