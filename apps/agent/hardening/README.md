# Agent hardening (issue #21)

Reliability + prompt-injection + approval-boundary layer per
docs/05-NEMOTRON.md (Reliability + Agent tests N02/N03/N05/N07/N08) and
docs/08 threat 2/7.

## Layers

| Module | Defense |
|---|---|
| `untrusted.py` | `UntrustedText` fences SSID/OCR/filename/log strings as delimited untrusted data; `looks_like_injection` flags instruction-like content for audit (detection ≠ the defense — fencing + guards are) |
| `guard.py` | `ToolGuard`: name allowlist + **authority denylist** (`approve/execute/contain/delete/grant/shell/...` — agent may only *propose*), arg size caps, instruction-like content in privileged args, per-run call budget, identical-call loop detection. Full trace. |
| `output_guard.py` | `ModelOutputGuard`: assessment schema (assessment/evidence_ids/unknowns required), **forbidden authority claims** ("containment approved/executed/verified", "endpoint isolated", "I approved", "breach/exfiltration confirmed"), fabricated `evidence_id` citation rejection, missing-unknowns flag. `revise_on_contradiction()` downgrades hypotheses on contradictory evidence (N02). |
| `hardened.py` | `HardenedAgent`: installs guarded dispatch on an investigation agent's registry — every call passes `ToolGuard` first; `append_agent_assessment` payloads pass `ModelOutputGuard` **before** being recorded; violations rejected with reasons. |

## Acceptance mapping

- **SSID prompt injection fails (N03):** sensor strings fenced as
  `[UNTRUSTED DATA]`; even if model echoes them, `ToolGuard` denies any
  authority-bearing tool name and `ModelOutputGuard` rejects approval/
  execution claims in output.
- **Model cannot approve containment:** no approve/execute tool exists
  in the allowlist; denylist blocks names containing approve/execute/
  contain/etc. `propose_containment` remains proposal-only.
- **Contradictory evidence revises hypothesis (N02):**
  `revise_on_contradiction()` produces an auditable downgrade record.
- **Malformed responses (N05):** non-dict args, oversized strings,
  unexpected keys rejected at guard + registry layers.
- **Repeated calls:** identical tool+args > N → loop denial.
- **Model unavailable:** inner agent degrades (see #20); guard layers
  are model-agnostic and don't depend on inference being up — manual
  command-center workflow unaffected (N04).
- **No false verified-isolation claim (N07):** FORBIDDEN_CLAIMS regex
  blocks "verified isolation/containment" phrasing in agent output;
  verification is a separate executor concern (#34).
- **Cites actual evidence (N08):** fabricated `evidence_id`s rejected
  when the known-evidence set is provided.

## Tests

```sh
cd apps/agent/hardening && PYTHONPATH=src python3 -m pytest tests/ -q
```

14 tests: fencing + injection detection, authority-tool denial,
proposal-vs-execute boundary, budgets, loop detection, arg caps,
fabricated citations, forbidden claims, clean-assessment accept,
contradiction revision, hardened-agent integration (blocked
`approve_containment`, rejected bad assessment).

## NOT done

- `HardenedAgent.install()` monkey-patches the inner registry — works
  with the #20 agent shape; a first-class middleware hook in the agent
  would be cleaner once branches merge.
- Fencing is structural, not semantic — a sufficiently creative model
  could still be manipulated via allowed read tools' *content*; the
  authority boundary (no approve/execute tools) is the hard guarantee.
- Injection regression corpus (real malicious SSID/OCR fixtures from
  the demo AP) pending live captures.
