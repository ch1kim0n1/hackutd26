# SENTINEL HIVE / Phantom Patrol — Python API facade (issue #96)

FastAPI entrypoint that exposes the **existing** Python security
services over HTTP. It wraps them — no policy, RBAC, evidence, or audit
logic is rewritten here.

> **State is in-memory and ephemeral.** Restart loses all users,
> incidents, proposals, and sessions. This is a development facade, not
> a deployment. Nothing here claims production persistence.

## Services wrapped

| Concern | Existing package (reused) |
|---|---|
| Identity / RBAC / sessions / access audit | `apps/identity` |
| Incident records, state machine, timeline, packet export | `apps/incident_records` |
| Scope matrix / CIA findings | `apps/scope_matrix` |
| Containment proposals, approvals, SoD, fingerprints | `apps/containment/policy` |
| Executor outbox pickup (mock lab adapters) | `apps/containment/executor` |
| Hash-chained response audit | `apps/containment/audit` |
| Investigation agent (scripted model — no live Nemotron yet) | `apps/agent/investigator` |

## Run

```sh
cd apps/api
PYTHONPATH=src python3 -m uvicorn sentinel_api.app:app --port 8000
# or with the repo's service src dirs auto-added (paths.py does this):
python3 -m uvicorn sentinel_api.app:app --app-dir src --port 8000
```

`paths.py` appends every `apps/**/src` to `sys.path`, so sibling
packages resolve without installation.

## Configuration (env vars — names only, never commit values)

| Var | Default | Purpose |
|---|---|---|
| `SENTINEL_API_SEED` | `1` | seed demo principals on boot (`0` = empty) |
| `SENTINEL_POLICY_SECRET` | random per boot | HMAC fingerprint secret for approvals; ephemeral if unset (restarts invalidate pending proposals — consistent with in-memory state) |
| `SENTINEL_POLICY_TARGETS` | built-in lab allowlist | comma-separated containment target allowlist |

## Seeded dev principals

| Username | Role | Login |
|---|---|---|
| `root-admin` | admin | `POST /auth/login` |
| `commander` | commander | `POST /auth/login` |
| `responder` | responder | `POST /auth/login` (needs per-incident scope grant) |
| `observer` | observer | `POST /auth/login` (read-only, needs scope) |
| `agent-01` | agent (machine) | cannot human-login; provisioned token seeded |
| `executor-01` | executor (machine) | cannot human-login |

Dev-mode login accepts any password (`password_ok=True`) — there is no
credential store. Machine principals authenticate via provisioned bearer
tokens, mirroring device-token provisioning in production.

## Example session

```sh
# login
TOKEN=$(curl -s localhost:8000/auth/login -H 'content-type: application/json' \
  -d '{"username":"commander"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
AUTH="Authorization: Bearer $TOKEN"

curl -s localhost:8000/healthz
curl -s localhost:8000/incidents -H "$AUTH"

# create + triage an incident
IID=$(curl -s localhost:8000/incidents -H "$AUTH" -H 'content-type: application/json' \
  -d '{"title":"Rogue AP near rack-01","severity":"high","zone_id":"rack-01"}' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["incident_id"])')
curl -s localhost:8000/incidents/$IID/transition -H "$AUTH" -H 'content-type: application/json' \
  -d '{"to_state":"triage","expected_version":1,"reason":"initial look"}'

# scripted investigation (deterministic; live Nemotron is Milestone 4)
curl -s localhost:8000/investigations -H "$AUTH" -H 'content-type: application/json' \
  -d "{\"incident_id\":\"$IID\",\"brief\":\"unknown BLE device\"}"

# agent proposes containment -> commander approves (SoD + fingerprint)
# (agent token is provisioned at seed; see state.seed())
```

## API surface

- `GET /healthz`, `GET /readyz`
- `POST /auth/login`, `POST /auth/logout`
- `GET/POST /users`, `POST /users/{id}/revoke|role|scope` (admin)
- `GET/POST /incidents`, `GET/PATCH /incidents/{id}`,
  `POST /incidents/{id}/transition|notes|evidence`,
  `GET /incidents/{id}/packet`
- `GET /incidents/{id}/scope`, `POST /scope/entries`
- `POST/GET /investigations`
- `POST/GET /proposals`, `GET /proposals/{id}`, `POST /approvals`
- `GET /actions/approved`, `POST /executor/execute`
- `GET /audit`

Every response carries `provenance: "LIVE"` (service-derived, not a
fixture) and `state_backend: "in-memory"`. Authorization failures return
403 with the service's denial reason; every check is written to the
identity audit trail.

## Tests

```sh
cd apps/api && PYTHONPATH=src python3 -m pytest tests/ -q
# 18 tests: health, auth denial, machine-login denial, scoped RBAC,
# version conflicts, invalid transitions, schema rejection (422),
# evidence/packet, scope entries, scripted investigation, proposal
# allowlist, SoD self-approval denial, fingerprint rejection,
# executor role gates, audit restrictions.
```

## Known limitations / blockers

- In-memory only — no SpacetimeDB coupling (Devin 2 / issue #97 owns
  persistence).
- Investigator runs a **scripted** model + fake backends; live Nemotron
  transport is issue #111 (Milestone 4). API key must never be committed.
- Executor uses `MockLabAdapter`/`MockVerifyAdapter` — lab-only semantics,
  no real firewall/switch actuation.
- No chat endpoints in this facade (chat service exists; API surface can
  grow in a later issue).
- Login has no password verification — dev convenience only.
