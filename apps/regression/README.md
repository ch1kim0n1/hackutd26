# apps/regression — workflow regression scenarios (#110)

End-to-end scenarios wiring the merged prevention/interception/
mitigation packages. Each returns an evidence chain for audit
continuity checks.

- `prevention_scenario()`: posture findings -> risk prioritize ->
  incident candidate -> hardening propose -> commander approve ->
  execute -> VERIFIED
- `interception_scenario()`: attacker flow -> redirect to decoy,
  bad-actor -> block, ops -> allow; evidence per route
- `mitigation_scenario()`: approved quarantine_vlan -> ExecutorService
  -> NodeLabAdapter -> HealthProbeVerify -> VERIFIED -> release ->
  reachable again
- `negative_checks()`: expired approval, self-approval, fingerprint
  replay, verify-lie -> FAILED, non-allowlisted fix — all denied

## Tests

4 pytest checks covering all scenarios + negatives.
