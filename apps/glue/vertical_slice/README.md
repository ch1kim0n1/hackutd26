# GLUE-01 device→SpacetimeDB vertical slice (#48)

In-memory implementation of the docs/04 pipeline: device event →
HMAC-authenticated collector → normalized observation (server-bound
zone, provenance, trace_id) → reducer (event_id dedup, incident-scoped
fan-out, staleness, latency) → authorized subscribers.

## Tests

```sh
cd apps/glue/vertical_slice && PYTHONPATH=src python3 -m pytest tests/ -q  # 7 passed
```

Covers: end-to-end 2-subscriber delivery, duplicate suppression, bad
creds/unknown device, zone-from-key (claim ignored), staleness flag,
incident-scoped delivery, latency measurement.

## NOT done — needs real deployment

- Reducer is in-memory; production = SpacetimeDB tables/reducers.
- No real hardware event, no two-browser latency demo, no committed
  screenshots/trace IDs — depends on #39/#40/#41 infra.
- `observed_epoch` is a test convenience; production parses RFC3339
  `observed_at`.
