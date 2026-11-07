# UX-29 RF channel intelligence + evidence drilldown (#29)

`rf_intel.py`: builds channel heatmap, BSSID inventory, RSSI time
series strictly from real scan outputs — LIVE/REPLAY provenance
enforced, timestamps everywhere, permission+incident-scope checked
evidence_for(). Only observed channels/BSSIDs appear — no fabricated
spectrum.

## Tests
`PYTHONPATH=src python3 -m pytest tests/ -q` -> 6 passed

## NOT done
Data layer only — React rendering pending #28 twin; live Kismet/
ESP32 feeds need deployed sensors; incident_links populated by
correlator at integration.
