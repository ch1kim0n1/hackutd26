# GLUE-05 approval->containment->verification closed loop (#52)

Chain: Proposal -> ApprovalService (role+separation-of-duties+TTL) ->
policy consume (fingerprint+replay) -> idempotent Outbox -> LabExecutor
(allowlist, lab-targets only) -> IndependentVerifier (separate probe) ->
scope/chat updates. Every stage timeline-audited; verify failure ->
FAILED posted to team chat, never silent.

## Tests
`PYTHONPATH=src python3 -m pytest tests/ -q` -> 9 passed

## NOT done
In-memory services; real firewall/switch + SpacetimeDB outbox pending
#34/#43-46; no live demo.
