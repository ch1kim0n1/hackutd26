"""ControlPlane — service registry enforcing the access matrix +
independent-of-lab health (docs/06 R01).

Key property: lab outage (DNS/DHCP/IdP down, LAN disconnected) does NOT
affect management-side services — they never depended on lab identity.
Containment calls require a server-side approval token; a direct
browser request without one is refused (W01e)."""
from __future__ import annotations

import hashlib
import hmac
import time
import uuid

from .topology import Principal, Segment, Service, authorize, requires_token

APPROVAL_TTL_S = 120.0


class ControlPlane:
    def __init__(self, approval_secret: bytes = b"dev-only-not-secret",
                 clock=time.time):
        self.clock = clock
        self.secret = approval_secret
        self.approved_actions: dict[str, dict] = {}
        self.sessions: dict[str, dict] = {}   # token -> session
        self.health = {s.value: "up" for s in Service}
        self.lab_connected = True

    # ---------------- health ----------------
    def lab_link_state(self) -> str:
        """Management services report lab state honestly — stale marker
        when disconnected, never fabricated 'all clear'."""
        return "connected" if self.lab_connected else "disconnected_stale"

    def service_health(self, service: Service) -> dict:
        return {"service": service.value, "status": self.health[service.value],
                "lab_link": self.lab_link_state()}

    # ---------------- access ----------------
    def check_access(self, segment: Segment, principal: Principal,
                     service: Service, token: str | None = None) -> tuple[bool, str]:
        ok, reason = authorize(segment, principal, service)
        if not ok:
            return False, reason
        if requires_token(service):
            if not token or not self._valid_session(token, principal):
                return False, "valid session token required"
        return True, "ok"

    # ---------------- sessions (W01d: revoke immediate) ----------------
    def login(self, principal: Principal, ttl_s: float = 3600) -> str:
        token = f"sess-{uuid.uuid4().hex[:16]}"
        self.sessions[token] = {"principal": principal.value,
                                "expires_at": self.clock() + ttl_s,
                                "revoked": False}
        return token

    def revoke_session(self, token: str) -> None:
        if token in self.sessions:
            self.sessions[token]["revoked"] = True

    def _valid_session(self, token: str, principal: Principal) -> bool:
        s = self.sessions.get(token)
        if not s or s["revoked"]:
            return False
        if self.clock() > s["expires_at"]:
            return False
        return s["principal"] == principal.value

    # ---------------- containment gate (W01e) ----------------
    def request_containment(self, segment: Segment, principal: Principal,
                            session_token: str | None,
                            action: dict) -> tuple[bool, str, str | None]:
        """Direct browser->containment calls are refused; only a
        server-side APPROVED action (from #33 policy) may proceed.
        Returns (allowed, reason, approval_id)."""
        ok, reason = self.check_access(segment, principal, Service.CONTAINMENT,
                                       token=session_token)
        if not ok:
            return False, reason, None
        # must reference a server-side approval — never client-claimed
        approval_id = action.get("approval_id", "")
        appr = self.approved_actions.get(approval_id)
        if appr is None:
            return False, "no server-side approval for this action", None
        if appr["expires_at"] < self.clock():
            return False, "approval expired", approval_id
        if appr["target_fingerprint"] != self._action_fingerprint(action):
            return False, "action does not match approved fingerprint", approval_id
        return True, "approved action accepted", approval_id

    def register_approval(self, approval_id: str, action: dict,
                          ttl_s: float = APPROVAL_TTL_S) -> None:
        """Called by the approval service (#33) — server-side only."""
        self.approved_actions[approval_id] = {
            "expires_at": self.clock() + ttl_s,
            "target_fingerprint": self._action_fingerprint(action),
        }

    def _action_fingerprint(self, action: dict) -> str:
        material = f"{action.get('action_type','')}|{action.get('target_id','')}|" \
                   f"{action.get('incident_id','')}"
        return hmac.new(self.secret, material.encode(),
                        hashlib.sha256).hexdigest()
