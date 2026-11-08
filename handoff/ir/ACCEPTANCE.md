# IR subsystem — acceptance evidence index (#44)

Maps issue #44 "verify subsystem acceptance and engineering handoff"
criteria to merged work.

## Delivered (merged PRs)

| Issue | PR | Package | Tests | Status |
|---|---|---|---|---|
| #25 Incident records | #71 | `apps/incident_records/` | 6 pytest → W03a–e | PARTIAL — in-memory, no live 2-user demo |
| #26 Scope matrix | #72 | `apps/scope_matrix/` | 5 pytest → W04a–e | PARTIAL — in-memory, evidence taxonomy ours |
| #27 Live chat | #73 | `apps/incident_chat/` | 6 pytest → W05a–d | PARTIAL — in-memory, no offline delivery |

## Acceptance criteria status

- [x] Incident records — severity/confidence/owner/zone/provenance/
  version; 9-state machine; optimistic-concurrency edits (visible
  VersionConflict); append-only timeline; JSON+MD packet export
- [x] Scope matrix — per-asset/dataset CIA dims independent; 10
  statuses (`unknown` preserved, never→unaffected); evidence gate
  (RF/AP can't confirm breach); versioned snapshots
- [x] Chat — per-incident rooms + restricted command channel;
  membership/role server-side; nonce dedup; presence/unread;
  reconnect history; system posts w/ action+evidence links;
  sanitization
- [ ] Live SpacetimeDB tables + reducers — BLOCKED
- [ ] Two-browser live editing/chat demo — BLOCKED
- [ ] W03/W04/W05 REAL-mode recorded PASS — BLOCKED

## Reproduce tests

```sh
cd apps/incident_records && PYTHONPATH=src python3 -m pytest tests/ -q  # 6
cd apps/scope_matrix && PYTHONPATH=src python3 -m pytest tests/ -q       # 5
cd apps/incident_chat && PYTHONPATH=src python3 -m pytest tests/ -q      # 6
```
