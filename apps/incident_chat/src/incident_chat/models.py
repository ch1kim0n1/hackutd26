"""Incident chat model — docs/06 R05/W05, `chat_messages` docs/04.

Rooms are per-incident (+ optional incident-command channel). Messages
carry client_nonce for dedup, seq for ordered history/reconnect,
sender identity+role from SERVER-side principal — never client claims.
Input is sanitized: plain text only, no markup/attachments."""
from __future__ import annotations

import html
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum

MAX_BODY = 4000


class RoomKind(str, Enum):
    INCIDENT = "incident"          # per-incident room
    COMMAND = "command"            # incident-command channel (restricted)


class PrincipalRole(str, Enum):
    ADMIN = "admin"
    COMMANDER = "commander"
    RESPONDER = "responder"
    OBSERVER = "observer"
    AGENT = "agent"
    SYSTEM = "system"


# who may JOIN each room kind (server-side membership)
JOIN_RULES: dict[RoomKind, set[PrincipalRole]] = {
    RoomKind.INCIDENT: {PrincipalRole.ADMIN, PrincipalRole.COMMANDER,
                        PrincipalRole.RESPONDER, PrincipalRole.OBSERVER,
                        PrincipalRole.AGENT},
    RoomKind.COMMAND: {PrincipalRole.ADMIN, PrincipalRole.COMMANDER},
}

# who may POST in each room kind
POST_RULES: dict[RoomKind, set[PrincipalRole]] = {
    RoomKind.INCIDENT: {PrincipalRole.ADMIN, PrincipalRole.COMMANDER,
                        PrincipalRole.RESPONDER, PrincipalRole.AGENT,
                        PrincipalRole.SYSTEM},
    RoomKind.COMMAND: {PrincipalRole.ADMIN, PrincipalRole.COMMANDER,
                       PrincipalRole.SYSTEM},
}


@dataclass
class Room:
    room_id: str
    incident_id: str
    kind: RoomKind
    members: dict[str, dict] = field(default_factory=dict)  # user_id -> presence
    messages: list["Message"] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


@dataclass
class Message:
    msg_id: str
    room_id: str
    seq: int
    at: float
    sender_id: str
    sender_role: PrincipalRole
    kind: str                    # "chat" | "system"
    body: str
    client_nonce: str = ""
    links: dict = field(default_factory=dict)  # e.g. {"action_id": ..., "evidence_id": ...}


_TAG_RE = re.compile(r"<[^>]+>")


def sanitize(text: str) -> str:
    """Untrusted input: strip markup, collapse whitespace, bound length.
    Output is PLAIN TEXT — renderers must escape, never innerHTML."""
    text = _TAG_RE.sub("", text)          # remove any tags
    text = html.unescape(text)            # decode entities safely
    text = re.sub(r"\s+", " ", text).strip()
    return text[:MAX_BODY]
