# AI engineering handoff (#42)

## What exists

- `apps/agent/nemotron_client/` — pinned Nemotron endpoint/model config
  (env-required), tool-calling chat client, latency log, retry/
  auth-fail-fast.
- `apps/agent/investigator/` — 9-tool allowlisted registry w/ scope
  checks, agent loop w/ budgets + evidence citations, proposal-only
  containment.
- `apps/agent/hardening/` — untrusted fencing, ToolGuard, ModelOutputGuard,
  contradiction revision.
- `apps/glue/correlation_agent/` — CORR01→queue→tool worker→grounded
  report pipeline (open PR #75).

## Integration touchpoints (docs/05)

- Agent reads via dashboard API; proposes via containment API
  (proposal-only — never executes).
- Model output guarded before any citation/report is trusted.
- Containment proposals flow to #33 policy → #52 closed loop; agent
  can never self-approve.

## Known limitations / risks

- **No live Nemotron endpoint** — all agent behavior tested with
  scripted/fake models; real tool-calling unverified.
- Tool backends are in-memory fakes — production binds to SpacetimeDB
  reducers (unmerged data layer).
- Prompt-injection defenses are heuristic guards — red-team the guards
  against a live model before trusting them.

## Next steps

1. Provision `NVIDIA_API_KEY` + pinned model endpoint; run client smoke.
2. Bind tool registry to real SpacetimeDB reducers.
3. Replay GLUE-02 (#49) with live model; verify ≥3 real tool calls,
   citations, unknowns, alternates.
4. Adversarial injection suite against live model outputs.
