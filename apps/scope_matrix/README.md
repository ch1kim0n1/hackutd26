# Compromised-data scope matrix (issue #26)

Winstead R04 — `docs/06-WINSTEAD-COMPLIANCE.md`, `scope_entries`
contract in `docs/04`.

## Components

- **`models.py`** — `ScopeStatus` (10 statuses incl. `unknown`),
  `CIA` confidentiality/integrity/availability tracked independently,
  `STATUS_CIA` impact mapping, `STRONG_EVIDENCE` vs `WEAK_EVIDENCE`
  classification, `ScopeEntry`, immutable `ScopeSnapshot`.
- **`service.py`** — `ScopeMatrix`: `add_entry`, `set_status` (per-CIA,
  version-checked, **evidence-gated**), `set_impact` (record counts +
  window), `link_evidence`, `snapshot` (append-only history), audit log.

## Key safety rules

- **RF/AP/observation anomalies can NEVER confirm a breach** —
  `CONFIRMED` statuses (confirmed_exposed/exfiltrated/encrypted_locked/
  corrupted) require `STRONG_EVIDENCE` kinds (edr_alert, auth_log,
  ransom_note, exfil_capture, backup_diff, manual_verified…);
  `InsufficientEvidence` raised otherwise.
- **`unknown` is preserved** — never silently converted to
  `unaffected`; each CIA dimension updates independently.
- **Suspected ≠ confirmed** — weak evidence justifies
  `suspected_exposed` only.
- **Versioned + snapshotted** — stale writes → `VersionConflict`;
  `snapshot()` freezes point-in-time state; earlier snapshots never
  retroactively change.

## W04 acceptance mapping

- **W04a** commander edit → responder reads live; stale writer conflicts
- **W04b** ransomware (encrypted_locked on C+A, integrity unaffected)
  vs exfiltration (exfiltrated on C only) — distinct statuses + distinct
  record counts/windows
- **W04c** CIA dimensions independently editable; untouched dimension
  stays `unknown`
- **W04d** evidence gating: rf_frame/wifi_ap → `InsufficientEvidence`
  on confirmed; suspected allowed; strong evidence upgrades; all audited
- **W04e** snapshots preserve suspected→exfiltrated progression

## Tests

```sh
cd apps/scope_matrix && PYTHONPATH=src python3 -m pytest tests/ -q   # 5 passed
```

## NOT done

- In-memory — production = SpacetimeDB `scope_entries` table + reducers.
- No live multi-client demo; live-update semantics proven at service
  layer (same-store read-after-write).
- Evidence-kind taxonomy is ours — map to real artifact types at
  integration.
