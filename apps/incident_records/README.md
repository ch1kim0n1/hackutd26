# Incident records, timeline, export (issue #25)

Winstead R03 "Incident Documentation" — `docs/06-WINSTEAD-COMPLIANCE.md`,
`incidents`/`evidence`/`audit_events` contracts in `docs/04`.

## Components

- **`models.py`** — `Incident` (title/summary/state/severity/confidence/
  owner/zone/provenance/version), `IncidentState` 9-state machine with
  `TRANSITIONS` allowlist, `EvidenceRef`, `TimelineEvent`,
  `VersionConflict`, `InvalidTransition`.
- **`service.py`** — `IncidentService`:
  - `create` — seeds `created` timeline event
  - `update`/`assign` — **optimistic concurrency**: caller supplies
    `expected_version`; stale → `VersionConflict` (visible, never
    silent overwrite); editable-field allowlist enforced
  - `transition` — state machine + version check + timeline
  - `add_note`, `link_evidence` — append-only history
  - `export_packet`/`export_markdown` — full record + evidence +
    timeline + provenance; export itself recorded in timeline

## W03 acceptance mapping

- **W03a** two-user live editing: A edits v1→v2; B's stale v1 write →
  `VersionConflict(current_version)`; B retries fresh → both edits
  preserved, no overwrite
- **W03b** evidence + history: evidence links carry kind/note/added_by;
  timeline append-only, seq-ordered
- **W03c** state machine: legal transitions pass; `investigating→closed`
  and any exit from terminal states rejected
- **W03d** packet export: JSON packet w/ provenance + evidence +
  timeline + notes; Markdown rendering; export audited in timeline

## Tests

```sh
cd apps/incident_records && PYTHONPATH=src python3 -m pytest tests/ -q   # 6 passed
```

## NOT done

- In-memory store — production = SpacetimeDB `incidents` table w/
  version column + reducers enforcing same checks server-side.
- No live two-browser demo — conflict semantics proven at service
  layer; UI surfacing (conflict banner) is dashboard work.
- Authorization (who may edit/approve) delegates to #23 identity —
  reducers must call `authorize()` before mutations.
