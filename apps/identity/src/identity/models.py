"""Identity + RBAC models — docs/06 R02 role matrix, docs/04 role matrix."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum


class Role(str, Enum):
    ADMIN = "admin"
    COMMANDER = "commander"
    RESPONDER = "responder"
    OBSERVER = "observer"
    AGENT = "agent"        # machine principal — non-interactive
    DEVICE = "device"      # machine principal — non-interactive
    EXECUTOR = "executor"  # machine principal


class PrincipalKind(str, Enum):
    HUMAN = "human"
    MACHINE = "machine"    # agent/device/executor — cannot human-login


MACHINE_ROLES = {Role.AGENT, Role.DEVICE, Role.EXECUTOR}
HUMAN_ROLES = {Role.ADMIN, Role.COMMANDER, Role.RESPONDER, Role.OBSERVER}


class UserStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


@dataclass
class User:
    user_id: str
    username: str
    role: Role
    kind: PrincipalKind
    incident_scope: set[str] = field(default_factory=set)  # empty=none/all-admin
    status: UserStatus = UserStatus.ACTIVE
    created_at: float = field(default_factory=time.time)
    created_by: str = ""

    @property
    def can_human_login(self) -> bool:
        return self.kind == PrincipalKind.HUMAN and \
            self.role in HUMAN_ROLES and self.status == UserStatus.ACTIVE


@dataclass
class AuditRecord:
    seq: int
    at: float
    actor_id: str
    operation: str          # user_add|user_revoke|role_change|scope_change|access_check
    target_id: str
    detail: dict = field(default_factory=dict)


class Access(str, Enum):
    READ_INCIDENT = "read_incident"
    WRITE_INCIDENT = "write_incident"       # edit/annotate/assign
    UPLOAD_EVIDENCE = "upload_evidence"
    POST_CHAT = "post_chat"
    READ_CHAT = "read_chat"
    APPROVE_ACTION = "approve_action"
    PROPOSE_ACTION = "propose_action"
    MANAGE_USERS = "manage_users"
    MANAGE_ROLES = "manage_roles"
    READ_EVIDENCE = "read_evidence"
    READ_UNSCOPED = "read_unscoped"          # cross-incident reads


# Role -> allowed Access set (docs/04 + docs/06 R02)
ROLE_MATRIX: dict[Role, set[Access]] = {
    Role.ADMIN: {a for a in Access},
    Role.COMMANDER: {
        Access.READ_INCIDENT, Access.WRITE_INCIDENT, Access.UPLOAD_EVIDENCE,
        Access.POST_CHAT, Access.READ_CHAT, Access.APPROVE_ACTION,
        Access.PROPOSE_ACTION, Access.READ_EVIDENCE,
        Access.MANAGE_ROLES,  # cannot manage users per strict reading;
                              # docs allow assign/revoke roles -> keep
    },
    Role.RESPONDER: {
        Access.READ_INCIDENT, Access.WRITE_INCIDENT, Access.UPLOAD_EVIDENCE,
        Access.POST_CHAT, Access.READ_CHAT, Access.PROPOSE_ACTION,
        Access.READ_EVIDENCE,
    },
    Role.OBSERVER: {
        Access.READ_INCIDENT, Access.READ_CHAT, Access.READ_EVIDENCE,
    },
    Role.AGENT: {
        Access.READ_INCIDENT, Access.PROPOSE_ACTION, Access.POST_CHAT,
        Access.READ_CHAT,
    },
    Role.DEVICE: set(),          # telemetry ingest only — no API access
    Role.EXECUTOR: {
        Access.READ_INCIDENT,   # reads approved action context only
    },
}
