# GLUE-04 realtime twin feed (#51)

`twin_feed.py`: unified feed for digital twin — rover poses, RF scans,
photos, timeline, scope, chat. Every item: provenance
(LIVE/REPLAY/SYNTHETIC enforced), timestamp, staleness flagged at
read, incident-scoped subscriptions server-side. `rf_scans()` returns
only real scan outputs — no fabricated spectrum.

## Tests
`PYTHONPATH=src python3 -m pytest tests/ -q` -> 6 passed

## NOT done
Data contract only — React/R3F rendering is #28; live SpacetimeDB
subscriptions pending deployment; no two-user live demo.
