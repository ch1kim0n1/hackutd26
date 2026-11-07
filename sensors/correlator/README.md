# RF correlator (issue #14)

Normalizes authorized RF observations and correlates anomalies per
`docs/03-ROBOTICS-RF.md` and `docs/04-DATA-AND-INTERFACES.md`.

## Pipeline

```
canonical puck events ─┐
Kismet kismetdb JSONL ─┼─> adapters.py ─> NormalizedObservation
ESP32 serial lines ────┘        │
                                v
                          dedup.py (30s window, stats only)
                                │
                                v
                          correlator.py
                     RF01 / PHY01 / CORR01 -> Alert + IncidentCandidate
```

## Rules (docs/03)

| Rule | Fires when | Severity |
|---|---|---|
| RF01 | known SSID + unexpected BSSID in ≥2 scans (same zone) | medium |
| PHY01 | cabinet opens with `authorized=false` (outside maintenance) | high |
| CORR01 | RF01 + PHY01 same zone within 120 s | high → incident candidate |

- **Maintenance suppression:** `cabinet_contact_open` with
  `authorized=true` is recorded as a track but produces **no PHY01 and no
  CORR01** — approved maintenance cannot false-claim a breach.
- **Unknown SSID ≠ RF01:** a BSSID on an SSID not in the inventory at all
  is a new network, not a known-SSID anomaly.
- **Cooldown:** identical rule+summary refires suppressed for 300 s.
- **Honesty:** every alert carries `evidence_quality` (scan counts,
  sources, deltas, explicit "could be X" notes); incident candidates list
  `alternatives` and `unknowns`. Confidence is evidence quality, never
  model certainty. Nothing here asserts exfiltration or breach.

## Kismet adapter

`adapt_kismet_record` / `adapt_stream` read **already-collected**
kismetdb JSON-lines (`kismet.device.base.*`, `dot11.*` fields) — this
code performs no capture, no deauth, no third-party sniffing (docs/03,
charter exclusions). Only bring records from our own authorized Kismet
receiver.

## Usage

```sh
cd sensors/correlator
PYTHONPATH=src python3 -m pytest tests/ -q          # 10 tests

# replay the demo incident fixture
PYTHONPATH=src python3 -m correlator.cli \
    tests/fixtures/demo_incident.jsonl \
    --inventory config/inventory.json --zone rack-01 \
    --out evidence/demo-incident.json
```

## Files

- `src/correlator/adapters.py` — puck-event / Kismet normalization
- `src/correlator/correlator.py` — rule engine + cooldown + CORR01 join
- `src/correlator/dedup.py`, `inventory.py`, `models.py`
- `tests/fixtures/demo_incident.jsonl`, `demo_maintenance.jsonl`
- `config/inventory.json` — authorized BSSID inventory template

## Integration (docs/04)

- Input: observations already admitted by the authenticated collector
  (issue #13) or exported Kismet captures tagged with `zone_id`.
- Output: `Alert`/`IncidentCandidate` map to `alerts` + `incidents`
  reducers via `ingestObservation → raiseAlert → createIncident`.
- `device_offline`/health events pass through as `NormKind.OTHER` —
  no RF rules apply.

## NOT done — needs hardware/live capture

- Tests use synthetic fixtures + hand-built kismetdb records, **not**
  live Kismet output or real puck radios.
- Kismet field names are tolerant-extraction guesses; validate against a
  real kismetdb export when the capture station exists.
- CORR01 timing uses wall-clock at ingest; production should compare
  `observed_epoch` values end-to-end.
- Zone assignment for Kismet records is caller-supplied (`--zone`);
  per-receiver zone mapping is deployment config.
