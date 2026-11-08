# apps/hardening — policy-gated preventive hardening (#104)

Posture candidates -> bounded config fixes -> commander approval (SoD)
-> executor apply -> INDEPENDENT verification (re-read config; executor
ack never counts). TTL + HMAC fingerprint + replay/self-approval/expiry
denial. Mirrors apps/containment/policy rules.

## Allowlist

Only ALLOWED_FIXES keys with permitted values: ssh_password_auth=off,
auto_updates=on, snmp_community_write=off, mqtt_tls=on, mfa_required=on,
fw_profile=restricted-egress. Everything else rejected at propose().

## Adapter boundary

`NodeConfigAdapter` protocol: apply_fix + read_config. FixtureAdapter
for tests; live adapter plugs into #101 service control plane later.
Verification always re-reads, so a lying adapter -> FAILED.

## Tests

9 checks: lifecycle verified, allowlist, SoD, role gate, fingerprint
replay, expiry, state machine, verify-failure honesty, dedup.
