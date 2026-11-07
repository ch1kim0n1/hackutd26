"""IdentityService — admin-managed users + AuthorizationService.

Every privileged mutation is audited (append-only). Authorization is
enforced server-side: role matrix + per-incident scope + status check.
Revocation is immediate — checked on every call, no cache."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from .models import (
    Access,
    AuditRecord,
    PrincipalKind,
    ROLE_MATRIX,
    Role,
    User,
    UserStatus,
)


class AuthzDenied(PermissionError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass
class Decision:
    allowed: bool
    reason: str


class IdentityService:
    """Admin-managed identity store + authorization (docs/06 R02)."""

    def __init__(self, clock=time.time):
        self.clock = clock
        self.users: dict[str, User] = {}
        self.audit: list[AuditRecord] = []
        self._seq = 0
        self.sessions: dict[str, str] = {}  # token -> user_id
        self._bootstrap_admin()

    # ---------- audit ----------
    def _audit(self, actor_id: str, op: str, target_id: str,
               detail: dict | None = None) -> None:
        self._seq += 1
        self.audit.append(AuditRecord(
            seq=self._seq, at=self.clock(), actor_id=actor_id,
            operation=op, target_id=target_id, detail=detail or {}))

    def audit_trail(self, target_id: str | None = None) -> list[AuditRecord]:
        if target_id is None:
            return list(self.audit)
        return [a for a in self.audit if a.target_id == target_id]

    # ---------- bootstrap ----------
    def _bootstrap_admin(self) -> None:
        admin = User(user_id="admin-root", username="root-admin",
                     role=Role.ADMIN, kind=PrincipalKind.HUMAN,
                     incident_scope=set(), created_by="system")
        self.users[admin.user_id] = admin

    # ---------- admin ops (audited) ----------
    def add_user(self, actor_id: str, username: str, role: Role,
                 kind: PrincipalKind, incident_scope: set[str] | None = None
                 ) -> User:
        self._require_admin(actor_id)
        if username in {u.username for u in self.users.values()}:
            raise ValueError(f"username {username} already exists")
        u = User(user_id=f"usr-{uuid.uuid4().hex[:10]}",
                 username=username, role=role, kind=kind,
                 incident_scope=incident_scope or set(),
                 created_by=actor_id)
        self.users[u.user_id] = u
        self._audit(actor_id, "user_add", u.user_id,
                    {"username": username, "role": role.value,
                     "kind": kind.value, "scope": sorted(u.incident_scope)})
        return u

    def revoke_user(self, actor_id: str, target_id: str) -> None:
        self._require_admin(actor_id)
        u = self.users.get(target_id)
        if u is None:
            raise KeyError(target_id)
        u.status = UserStatus.REVOKED
        # kill all sessions immediately
        for tok, uid in list(self.sessions.items()):
            if uid == target_id:
                del self.sessions[tok]
        self._audit(actor_id, "user_revoke", target_id,
                    {"username": u.username})

    def change_role(self, actor_id: str, target_id: str, new_role: Role) -> None:
        self._require_admin(actor_id)
        u = self.users.get(target_id)
        if u is None:
            raise KeyError(target_id)
        old = u.role
        u.role = new_role
        self._audit(actor_id, "role_change", target_id,
                    {"from": old.value, "to": new_role.value})

    def set_incident_scope(self, actor_id: str, target_id: str,
                           scope: set[str]) -> None:
        self._require_admin(actor_id)
        u = self.users.get(target_id)
        if u is None:
            raise KeyError(target_id)
        u.incident_scope = set(scope)
        self._audit(actor_id, "scope_change", target_id,
                    {"scope": sorted(scope)})

    def _require_admin(self, actor_id: str) -> None:
        actor = self.users.get(actor_id)
        if actor is None or actor.status != UserStatus.ACTIVE \
                or actor.role != Role.ADMIN:
            raise AuthzDenied("manage_users requires active admin")

    # ---------- sessions ----------
    def login(self, username: str, password_ok: bool = True) -> str | None:
        """Human login only. Machine principals CANNOT login here —
        they authenticate via device tokens at the service boundary."""
        for u in self.users.values():
            if u.username == username:
                if not u.can_human_login:
                    self._audit(u.user_id, "access_check", u.user_id,
                                {"op": "human_login", "denied": "machine_or_inactive"})
                    return None
                if not password_ok:
                    return None
                tok = f"tok-{uuid.uuid4().hex[:16]}"
                self.sessions[tok] = u.user_id
                return tok
        return None

    def logout(self, token: str) -> None:
        self.sessions.pop(token, None)

    # ---------- authorization ----------
    def authorize(self, actor_id: str, access: Access,
                  incident_id: str | None = None) -> Decision:
        """Server-side check: status + role capability + incident scope.
        Every check is audited. Unknown incident scope NEVER grants."""
        u = self.users.get(actor_id)
        if u is None:
            return self._deny(actor_id, access, "unknown principal")
        if u.status != UserStatus.ACTIVE:
            return self._deny(actor_id, access, f"user {u.status.value}")
        caps = ROLE_MATRIX.get(u.role, set())
        if access not in caps:
            return self._deny(actor_id, access,
                              f"role {u.role.value} lacks {access.value}")
        # incident scoping: applies to incident-bound resources
        if incident_id is not None and access not in _UNSCOPED:
            if not self._in_scope(u, incident_id):
                return self._deny(actor_id, access,
                                  f"outside incident scope {incident_id}")
        self._audit(actor_id, "access_check", actor_id,
                    {"op": access.value, "incident": incident_id,
                     "allowed": True})
        return Decision(True, "ok")

    def _in_scope(self, u: User, incident_id: str) -> bool:
        # admin + machine principals with no explicit scope list are
        # not implicitly cross-incident: require explicit assignment OR
        # empty scope meaning "all" ONLY for admin/commander roles.
        if not u.incident_scope:
            return u.role in (Role.ADMIN, Role.COMMANDER)
        return incident_id in u.incident_scope

    def _deny(self, actor_id: str, access: Access, reason: str) -> Decision:
        self._audit(actor_id, "access_check", actor_id,
                    {"op": access.value, "allowed": False,
                     "reason": reason})
        return Decision(False, reason)


# Accesses that are NOT bound to a single incident (still role-gated)
_UNSCOPED = {Access.MANAGE_USERS, Access.MANAGE_ROLES}
