# Lab containment executor (issue #34)

Isolated credential-holding executor for the owned lab —
docs/08 threat 3 (rogue API/fake success) + threat 7 (race/retry),
docs/04 action states.

## Design

```
policy.approved_actions() (#33)
  -> Outbox.deliver(OutboxItem)     # idempotent by action_id
  -> Executor.run_once()
       STARTED -> lab.apply_isolation()   # lab-only creds, owned targets
       API_ACKED                          # adapter claim — NOT proof
       verify.isolation_effective() + target_reachable()==False
       -> VERIFIED | FAILED               # independent probe decides
```

- **`Outbox`** — only approved items enter; redelivery returns existing
  record (`skipped_duplicate`), expired approvals rejected before any
  lab contact. No other intake path exists.
- **`LabAdapter`** — holds lab firewall/switch credentials; applies
  isolation to OWNED targets only (allowlist enforced upstream #33).
  `MockLabAdapter` simulates rules + endpoint state for tests.
- **`VerifyAdapter`** — separate read-only probe (independent
  connectivity check). `api_response` is never consulted for the
  VERIFIED decision.
- **`ExecutionRecord.states_history`** — proposed/authorized/started/
  api_acked/verified/failed recorded distinctly for audit (#35).

## Threat-3 test (the important one)

`MockLabAdapter(lie_about_success=True)` returns `{"ok": true}` but
changes nothing → executor records **FAILED** with
`verification.effective=false`, never VERIFIED. An adapter that lies
cannot produce a false success.

## Tests

```sh
cd apps/containment/executor && PYTHONPATH=src python3 -m pytest tests/ -q
```

10 tests: verified isolation, fake-success→failed, adapter failure/
refusal, idempotent redelivery (apply once), expired approval rejected,
no-unapproved-execution, revert+verify, revert-failure.

## NOT done — needs real lab gear

- `LabAdapter`/`VerifyAdapter` are protocols + mocks; real SSH/REST
  bindings to the dedicated lab firewall/switch are deployment work.
- Verify probe is in-process mock; production = separate vantage
  (different host/creds) per docs/08 "independent connectivity
  verification".
- No credential storage implemented — lab creds live in the executor
  service's secret store, never in repo or agent process.
- Outbox is in-memory; production = SpACEDB outbox worker pattern
  (docs/04: external commands never as DB transaction side-effects).

## HTTP bridge (`containment_executor.service`)

`python -m containment_executor.service` exposes the executor over HTTP
for the gateway outbox worker (`EXECUTOR_WEBHOOK_URL`):

- `POST /execute` — body = module `payloadJson`; returns **200 only on
  `VERIFIED`** (independent probe passed), 502 on FAILED/other, 400 on
  malformed. Idempotent: redelivery of a verified action returns 200.
- `POST /revert` — `{"action_id": ...}` drives the #35 recovery path.
- `GET /healthz` — pending/record counts.
- Bearer auth via `EXECUTOR_TOKEN` (unset = open, lab only).

Env: `EXECUTOR_PORT` (8082), `EXECUTOR_TOKEN`, `EXECUTOR_ACTION_TTL_S`
(300), `EXECUTOR_FAIL_APPLY=1` / `EXECUTOR_LIE_ABOUT_SUCCESS=1` test
hooks for the honesty paths.

17 tests total (10 lib + 7 service): mapping, honest status codes,
idempotent redelivery, revert, live HTTP round-trip with auth.
