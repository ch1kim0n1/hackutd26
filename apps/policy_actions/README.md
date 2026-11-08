# apps/policy_actions — capability action verification (#113)

Package-level proof for the three defense capabilities. Module-side
chain (proposeAction -> recordApproval -> claimOutbox ->
recordExecutorOutcome -> verifyContainment) is covered by
spacetimedb/tests/smoke.ts; this suite proves each capability produces
an executor-ready doc + independently verified outcome.

- quarantine: ExecutorService + NodeLabAdapter + HealthProbeVerify on a
  real vpi node -> VERIFIED; lying adapter -> FAILED
- hardening: HardeningGate propose(agent) -> approve(commander) ->
  execute -> VERIFIED; expiry/self-approval/fingerprint-replay denied
- interception: DeceptionRouter redirect -> decoy evidence w/ full
  audit fields (trace/decision/flow/rule ids, provenance, enforcement)

Agent/actuator boundary: structural test asserts agent/* packages
contain no executor/adapter references; executor HTTP requires token.

Also fixed: ExecutorService._body now returns incident_id/action_type/
target_id (audit continuity for recordExecutorOutcome).
