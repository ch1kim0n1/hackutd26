# apps/honeypot_service — decoy service (#107)

Standalone decoy identity `decoy-01`: fake HTTP endpoints
(/ /login /config /firmware) with SYNTHETIC bait only. Every connection
logged (trace_id, client, method, path, payload sha256, UA/referer).
Loopback/LAN only, no real creds/data, no offensive capability.

Rover-host adapter boundary: same DecoyHandler can bind the rover's
interface when #108 deception routing lands; until then lab service.
Register `decoy-01` as `other` device type in SpacetimeDB seed for
identity tracking.

## Tests

7 checks: identity, bait endpoints, 404 logging, connection log,
POST body hash, synthetic-only, trace header.
