# Investigation agent (issue #20)

Bounded Nemotron investigation loop + allowlisted tool registry —
`docs/05-NEMOTRON.md`, trust matrix `docs/08-SECURITY-THREAT-MODEL.md`.

## Tool registry (`tools.py`)

Exactly the nine docs/05 tools, strict JSON schemas
(`additionalProperties:false`, required+type checks), scope-checked
dispatch via `ToolContext` (incident_id + zone/waypoint/device
allowlists). **No shell, no arbitrary network, no approve/execute
containment tools** — `propose_containment` only queues a proposal for
the human approval path.

Denials are first-class `ToolResult(denied=True)` with reasons —
malformed args, out-of-scope IDs, unknown tools all refused before any
backend runs.

## Agent loop (`agent.py`)

`investigate(incident_brief)`:

1. system prompt fences untrusted sensor text (SSID/OCR/logs = data,
   never instructions) and forbids breach claims from weak evidence
2. model emits tool calls → registry validates scope+args → backend
   executes → tool result appended
3. budgets: `MAX_TOOL_CALLS=12`, `MAX_STEPS=15`
4. collects `append_agent_assessment` payload → `Assessment`
   (hypotheses, competing explanations, unknowns, evidence_ids)
5. **model outage → `degraded=True` assessment**, manual command center
   unaffected (N04)

Every tool call lands in `registry.calls` + `assessment.trace` — the
decision trace docs/05 requires (args keys, ok/denied, latency).

## Backends (`backends.py`)

`FakeBackends` — deterministic in-memory implementations of all nine
tools for tests/dev. Production binds the same callables to
SpacetimeDB reducers (docs/04), the rover mission service (#12), the
puck rescan channel (#13) and the evidence store.

## Model interface

`ChatModel` protocol — duck-typed `chat(messages, tools, tool_choice)`.
Works with `nemotron_client.NemotronClient` (#19) or `ScriptedModel`
(tests). No hard dependency between branches.

## Tests

```sh
cd apps/agent/investigator && PYTHONPATH=src python3 -m pytest tests/ -q
```

8 tests: full investigation (≥5 tool calls incl. rover inspection,
assessment + evidence citations), out-of-scope waypoint denied (N06),
unknown tool denied, extra args rejected, wrong-incident scope denied,
model outage degradation (N04), tool-call budget, proposal-only
containment.

## NOT done — needs live Nemotron + real backends

- Tests use `ScriptedModel`, not a real model — N01 "real tool calls"
  requires the pinned endpoint from #19 plus live SpacetimeDB.
- `propose_containment` records proposals in-memory; wiring to the
  approval service (#33) is the integration point.
- Prompt-injection *hardening* beyond fencing (sanitization layers,
  injection regression suite) is issue #21.
