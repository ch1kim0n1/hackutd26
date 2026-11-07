# Admin-managed identities + incident-scoped RBAC (issue #23)

Winstead R02 — `docs/06-WINSTEAD-COMPLIANCE.md`, role matrix in
`docs/04-DATA-AND-INTERFACES.md`.

## Components

- **`models.py`** — `Role` (admin/commander/responder/observer/agent/
  device/executor), `PrincipalKind` (human/machine), `User` with
  per-incident `incident_scope`, `ROLE_MATRIX` capability map,
  `AuditRecord`.
- **`service.py`** — `IdentityService`:
  - `add_user` / `revoke_user` / `change_role` / `set_incident_scope` —
    admin-only, every mutation append-only audited.
  - `login` — **human principals only**; machine roles can never
    human-login (audited denial).
  - `authorize(actor, access, incident_id)` — server-side check:
    active status → role capability → per-incident scope. Every check
    audited allow or deny. Revocation kills sessions immediately.

## W02 acceptance mapping

- **W02a** add/revoke with audit trail (`user_add`, `user_revoke`,
  `role_change`, `scope_change`, `access_check` records)
- **W02b** observer read-only — no write/upload/chat-post/approve/
  propose/manage caps
- **W02c** incident scope — responder on inc-1 denied inc-2 reads AND
  writes; commander/admin implicit-all only with empty scope
- **W02d** immediate revocation — sessions destroyed, next authorize
  fails; suspended users denied
- **W02e** no device human login — `login("puck-a")`/`login("nemotron")`
  → None + audit; DEVICE role has zero API capabilities; agent can
  propose but never approve/manage

## Tests

```sh
cd apps/identity && PYTHONPATH=src python3 -m pytest tests/ -q   # 7 passed
```

## NOT done

- In-memory store — production backs onto the independent IdP +
  SpacetimeDB `users_and_roles`/`audit_events` tables (docs/04).
- Password/credential verification is a stub (`password_ok` flag) —
  real authN is the external IdP's job per docs/06.
- Subscription/evidence-fetch scoping hooks documented for reducers —
  reducers must call `authorize()` server-side, never trust frontend.
