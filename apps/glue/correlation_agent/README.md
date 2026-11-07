# GLUE-02 correlation->agent investigation (#49)

In-memory pipeline: `CorrelationEngine` (RF+physical co-occurrence ->
CORR01 candidate) -> incident queue -> `ToolWorker` (allowlisted tools,
traced calls) -> `InvestigationPipeline` producing evidence-grounded
reports.

Enforced: >=3 tool calls; citations must resolve to evidence store;
unknowns + alternate explanation mandatory; containment stays
proposal-only (no executor).

## Tests
`PYTHONPATH=src python3 -m pytest tests/ -q` -> 6 passed

## NOT done
Scripted tool driver (real Nemotron pending endpoint); in-memory
evidence/queue (prod = SpacetimeDB); no live rover/agent demo.
