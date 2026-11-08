# apps/quarantine — lab quarantine adapter (#109)

`NodeLabAdapter` implements the containment-executor LabAdapter protocol
against #101 vpi nodes' `/admin/isolate` endpoint. Whitelisted to the
module ActionType enum only; unknown action types raise
ActionNotApproved before any network call. `HealthProbeVerify` is the
independent verifier — GET /health from a separate vantage, reports
effective only on real 503+isolated, never trusts adapter ack.

vpi_service gained POST /admin/isolate|release + 503-on-/health-when-
isolated (lab control surface, isolated network only, no auth by
design — real adapters need real auth).

## Tests

7 checks: isolate->503, unapproved refused, release restores,
independent verify, unknown-node fail-closed, all 6 approved types,
no shell surface.
