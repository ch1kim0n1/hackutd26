# SEC engineering handoff (#43)

## What exists

- `apps/control_plane/` — topology (segments/principals/services,
  default-deny matrix, token-gated), LabRelay (outbound-only ingest,
  HMAC+dedup+seq+limits, fail-closed), ControlPlane (health,
  sessions, approval-fingerprint containment gate).
- `apps/identity/` — IdentityService: audited admin user/role/scope
  ops, human-only login, server-side authorize (status→role→scope),
  immediate revocation.
- `apps/security_tests/` — six boundary checks + PASS/FAIL report
  artifacts.
- `apps/glue/acceptance/` — W01–W05 runner (open PR #79).

## Integration touchpoints (docs/06, docs/08)

- Every service consults the access matrix — no embedded rules.
- Reducers/subscriptions call `IdentityService.authorize()`
  server-side; frontend checks never authoritative.
- Containment: proposal → approval (#33) → fingerprint consume →
  outbox → executor → independent verify (#52).
- Lab telemetry enters ONLY via relay; lab can never reach management.

## Known limitations / risks

- **Policy layer only** — no physical VLAN/firewall/mTLS deployed;
  "isolation" is enforced in code, not yet in cabling.
- In-memory sessions/users — production = independent OIDC IdP outside
  the lab network.
- Threat checks ran against doubles — same checks must run vs live
  endpoints for W01/W02 acceptance.

## Next steps

1. Provision management host/network per docs/06; terminate mTLS.
2. Deploy independent IdP; port IdentityService to it.
3. Apply network ACLs matching `topology.py` matrix; verify W01a–e
   physically.
4. Run `threat_tests` + acceptance runner in `live_endpoint` mode.
