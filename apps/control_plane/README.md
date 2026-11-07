# Independently isolated control plane (issue #22)

Winstead R01 "Secure and Isolated" — `docs/06-WINSTEAD-COMPLIANCE.md`.

## Components

| Module | Role |
|---|---|
| `topology.py` | Network segments (management/lab/bridge), principals, services, **default-deny access matrix**, token-gated services |
| `relay.py` | Outbound-only lab→mgmt observation relay: scoped expiring revocable device tokens, HMAC signatures, event_id dedup, seq monotonicity, size/rate limits, **fail-closed** on identity/policy/audit outage |
| `plane.py` | `ControlPlane`: service health independent of lab, session tokens (expiry+revoke), containment gate requiring **server-side approval** bound to action fingerprint |

## W01 acceptance mapping

- **W01a** adversarial lab endpoint: `LAB`/`LAB_HOSTILE` denied every
  service incl. relay-inbound; device creds can't reach human services.
- **W01b** lab DNS/IdP/LAN failure: management services stay `up`,
  lab link honestly reported `disconnected_stale`.
- **W01c** replay/forgery: duplicate event_id, bad HMAC, stale seq all
  rejected; relay fails closed when identity/audit deps down.
- **W01d** revoked/expired session: privileged ops denied immediately.
- **W01e** direct containment call: refused without server-side
  approval; approved actions fingerprint-bound to exact
  type+target+incident.

## Tests

```sh
cd apps/control_plane && PYTHONPATH=src python3 -m pytest tests/ -q   # 9 passed
```

## NOT done — needs real deployment

- Matrix/relay/plane are the policy + logic layer; physical VLAN/
  firewall rules, mTLS termination, SpacetimeDB private tables and the
  actual independently-hosted IdP are deployment work documented in
  docs/06. No real network isolation was performed here — the tests
  prove the *policy* denies the paths, not that cables are cut.
- Session store is in-memory; production = independent IdP (OIDC
  outside lab) per docs/06.
- Relay transport (MQTT/mTLS) is abstracted — device tokens + HMAC
  scheme ready for the real channel.
