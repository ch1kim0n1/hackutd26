# apps/deception — deception routing + evidence (#108)

`DeceptionRouter` wraps the #105 DecisionEngine with real HTTP routing:
suspicious flows matched by REDIRECT rules go to the #107 decoy
(`decoy-01`) instead of the real backend. Every route emits a
`deception-evidence/1` record: trace_id, decision_id, flow_id, rule_id,
action, outcome, decoy hit details, provenance.

Fail-closed: decoy unreachable or unconfigured -> 502/403, real backend
never contacted for redirected flows. `deception_policy()` builds the
standard block/redirect/default policy.

## Tests

7 checks: redirect->decoy w/ trace preserved, block, allow->backend,
decoy-down fail-closed, missing-decoy deny, evidence schema,
flow_id sanitization.
