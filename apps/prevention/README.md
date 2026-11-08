# apps/prevention — preventive incident workflow (#103)

Ranked posture findings -> prioritized incident CANDIDATES. Posture
weaknesses, not attacks: `kind=preventive_posture` distinguishes them
from attack-derived incidents. No containment, no attack claims.

## Pipeline

`risk_priority.prioritize()` output -> dedup (same node+check+detail
merges evidence) -> `PreventionPolicy` gate -> `IncidentCandidate` with
Nemotron-ready `context_bundle` (evidence_refs traceable, unknowns
explicit, constraints listed).

## Policy

Default: only `confirmed` + `high|critical` auto-file; `info|low` +
`unknown` held; rest queued. Conservative — posture never auto-acts.

## Tests

`PYTHONPATH=src:../posture/src:../risk_priority/src python3 -m pytest tests`
— 7 checks: schema, policy gating, dedup, determinism, unknown
preservation, citable bundle, threshold override.
