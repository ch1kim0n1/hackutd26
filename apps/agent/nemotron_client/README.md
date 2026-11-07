# Nemotron client (issue #19)

Pinned NVIDIA Nemotron inference client with structured tool calling —
`docs/05-NEMOTRON.md`, `docs/04-DATA-AND-INTERFACES.md`.

## What it does

- `NemotronConfig` — **pinned** model_id + endpoint; no defaults.
  `NEMOTRON_MODEL_ID` / `NEMOTRON_ENDPOINT` env required; API key via
  `NVIDIA_API_KEY` (or configured env name). Never committed.
- `NemotronClient.chat(messages, tools)` — OpenAI-compatible
  `/chat/completions` with `tools`/`tool_choice`; stdlib urllib transport
  (injectable for tests).
- `ToolSpec`/`ToolCall`/`ModelResponse` — structured tool-call types;
  unparseable arguments preserved raw (`_unparseable`) for downstream
  rejection, never silently coerced.
- `LatencyLog` — every call records model, latency_ms, tool names,
  attempt — the decision trace docs/05 requires.
- Retries with linear backoff on 429/5xx/transport errors; **401/403 fail
  fast** (auth won't heal by retrying); `ModelUnavailable` /
  `MalformedResponse` distinct failure modes for graceful degradation.

## Config pinning (docs/05 requirement)

```sh
export NEMOTRON_MODEL_ID="nvidia/<exact-tested-model-id>"
export NEMOTRON_ENDPOINT="https://integrate.api.nvidia.com/v1"
export NVIDIA_API_KEY="..."
```

The exact model/endpoint/latency must be pinned in deployment config
after a real smoke test — this client refuses to guess a default.

## Tests

```sh
cd apps/agent/nemotron_client && PYTHONPATH=src python3 -m pytest tests/ -q
```

8 tests: tool-call parse, unparseable args, 5xx retry→success,
retry exhaustion, auth fail-fast, malformed envelope, transport error
wrapping, and a **real HTTP roundtrip** through urllib against a local
server (verifies auth header + payload envelope).

## Integration touchpoints (docs/04)

- Consumed by the investigation agent (issue #20) — it owns the tool
  registry; this client only transports.
- `LatencyLog` entries + `ModelResponse.raw` feed the audit trail
  (docs/08) and SpacetimeDB agent-run records.

## NOT done — needs credentials + live endpoint

- No NVIDIA API key in this environment; **no real Nemotron invocation
  has occurred**. The pinned model ID must be verified against the
  actual available endpoint before demo signoff (acceptance: "evidence
  of real model invocation").
- Streaming, token-usage billing fields beyond passthrough, and
  structured-output (JSON-schema response_format) modes are not
  implemented — tool calling covers the agent loop.
- Rate-limit headers (Retry-After) are not parsed; backoff is fixed.
