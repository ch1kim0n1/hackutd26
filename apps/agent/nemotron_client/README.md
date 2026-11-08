# Nemotron client (issues #19, #111)

Pinned NVIDIA Nemotron inference client with structured tool calling —
`docs/05-NEMOTRON.md`, `docs/04-DATA-AND-INTERFACES.md`. Stdlib-only;
the model runs remotely — never on the rover.

## What it does

- `NemotronConfig` — **pinned** model_id + endpoint; no defaults.
  `NEMOTRON_MODEL_ID` / `NEMOTRON_ENDPOINT` env required; API key via
  env var name only. Never committed.
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

## Provider transport (issue #111)

`provider.py` wires the client into the investigation agent's
`ChatModel` contract with env-driven live/fake selection:

- `NemotronChatModel` — adapter: investigator's OpenAI-dict tool specs →
  `ToolSpec`; returns `ModelResponse` unchanged (already duck-compatible).
- `FakeNemotronModel` — deterministic script replay, zero network, for
  CI/dev.
- `build_chat_model(env=None, *, transport=None, fallback=None,
  scripted=())` → `(model, ProviderInfo)` — `ProviderInfo` is
  non-secret (mode, model_id, endpoint, key env-var *name*, reason).
- `validate_assessment(d)` — schema check on the serialized
  `Assessment` result (shape only; content authority stays with
  `ModelOutputGuard`).

### Mode selection (`SENTINEL_AGENT_MODEL`)

| Mode | Behavior |
|---|---|
| `auto` (default) | **live** only when model id + endpoint + key env var are ALL set; otherwise **fake** |
| `live` | Requires complete config — incomplete raises `RuntimeError` (fail loudly) |
| `fake` | Always offline; uses `fallback` if given, else `FakeNemotronModel` |

The API facade (`apps/api`) calls `build_chat_model(fallback=
ScriptedModel(...))`: live Nemotron when configured, the identical
deterministic scripted investigation otherwise. `/healthz` exposes the
non-secret `agent_provider` block so operators can verify the mode.

### Environment variables (names only — values never logged/committed)

| Variable | Purpose |
|---|---|
| `NEMOTRON_MODEL_ID` | Pinned model id — **required for live** |
| `NEMOTRON_ENDPOINT` | Base URL e.g. `https://integrate.api.nvidia.com/v1` — **required for live** |
| `NEMOTRON_API_KEY` | API key env var (preferred) |
| `NVIDIA_API_KEY` | Provider-required fallback key env var |
| `NEMOTRON_API_KEY_ENV` | Optional: name of a *different* env var holding the key |
| `SENTINEL_AGENT_MODEL` | `auto` \| `live` \| `fake` |
| `NEMOTRON_TIMEOUT_S` | Optional timeout override (default 30.0) |
| `NEMOTRON_MAX_RETRIES` | Optional retry override (default 2) |
| `NEMOTRON_MAX_TOKENS` | Optional token cap (default 2048) |
| `NEMOTRON_TEMPERATURE` | Optional temperature (default 0.2) |

**Secret safety:** key *values* are read lazily by
`NemotronConfig.api_key()` at request time, sent only as the
`Authorization: Bearer` header, and never appear in `ProviderInfo`,
logs, `LatencyLog`, exceptions, or this repository. Supply the key via
your environment or secret manager — never commit it.

## Config pinning (docs/05 requirement)

```sh
export NEMOTRON_MODEL_ID="nvidia/<exact-tested-model-id>"
export NEMOTRON_ENDPOINT="https://integrate.api.nvidia.com/v1"
export NEMOTRON_API_KEY="..."        # or NVIDIA_API_KEY
```

The exact model/endpoint/latency must be pinned in deployment config
after a real smoke test — this client refuses to guess a default.

## Tests

```sh
cd apps/agent/nemotron_client && PYTHONPATH=src python3 -m pytest tests/ -q
```

Client tests: tool-call parse, unparseable args, 5xx retry→success,
retry exhaustion, auth fail-fast, malformed envelope, transport error
wrapping, and a **real HTTP roundtrip** through urllib against a local
server (verifies auth header + payload envelope).

Provider tests (`test_provider.py`): env-mode selection, secret-leak
checks, dict-spec adaptation, fake replay/rewind, assessment validation,
and full `InvestigationAgent` runs over a local OpenAI-compatible HTTP
server — malformed body, 401 no-retry, 5xx retry, unreachable endpoint,
plus end-to-end `ToolGuard`/`ModelOutputGuard` denial of hostile tool
calls and fabricated assessment citations.

## Integration touchpoints (docs/04)

- Consumed by the investigation agent (issue #20) — it owns the tool
  registry; this client only transports.
- `LatencyLog` entries + `ModelResponse.raw` feed the audit trail
  (docs/08) and SpacetimeDB agent-run records.
- `HardenedAgent` (apps/agent/hardening) wraps the agent: every model
  tool call passes `ToolGuard` and every assessment write passes
  `ModelOutputGuard` — the transport adds no authority of its own.

## NOT done — needs credentials + live endpoint

- No NVIDIA API key in this environment; **no real Nemotron invocation
  has occurred**. Transport correctness is proven against a local
  OpenAI-compatible stub; the pinned model ID must be verified against
  the actual endpoint before demo signoff (acceptance: "evidence of
  real model invocation"). Set the env vars above and hit
  `POST /investigations` — `/healthz` will report `agent_provider.mode:
  "live"`.
- Streaming, token-usage billing fields beyond passthrough, and
  structured-output (JSON-schema response_format) modes are not
  implemented — tool calling covers the agent loop.
- Rate-limit headers (Retry-After) are not parsed; backoff is fixed.
