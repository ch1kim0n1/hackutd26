"""IncidentChat service — rooms, membership, posting, presence,
unread counts, reconnect history, nonce dedup (docs/06 R05/W05)."""
from __future__ import annotations

import time
import uuid

from .models import (
    JOIN_RULES,
    POST_RULES,
    Message,
    PrincipalRole,
    Room,
    RoomKind,
    sanitize,
)


class ChatDenied(PermissionError):
    pass


class ChatService:
    def __init__(self, clock=time.time):
        self.clock = clock
        self.rooms: dict[str, Room] = {}
        self._nonces: dict[str, str] = {}   # room_id|nonce -> msg_id
        self.users: dict[str, dict] = {}    # user_id -> {role, incidents}

    # ---------------- directory ----------------
    def register_user(self, user_id: str, role: PrincipalRole,
                      incident_ids: set[str] | None = None) -> None:
        """Server-side principal registry — role comes from IdP (#23),
        never from client claims."""
        self.users[user_id] = {"role": role,
                               "incidents": incident_ids or set()}

    # ---------------- rooms ----------------
    def create_room(self, incident_id: str, kind: RoomKind = RoomKind.INCIDENT
                    ) -> Room:
        room_id = f"{incident_id}:{kind.value}"
        if room_id in self.rooms:
            return self.rooms[room_id]
        r = Room(room_id=room_id, incident_id=incident_id, kind=kind)
        self.rooms[room_id] = r
        return r

    def _room(self, incident_id: str, kind: RoomKind) -> Room:
        rid = f"{incident_id}:{kind.value}"
        if rid not in self.rooms:
            raise ChatDenied(f"room {rid} does not exist")
        return self.rooms[rid]

    def _check_user_incident(self, user_id: str, incident_id: str) -> dict:
        u = self.users.get(user_id)
        if u is None:
            raise ChatDenied("unknown user")
        if incident_id not in u["incidents"] and \
                u["role"] not in (PrincipalRole.ADMIN,):
            raise ChatDenied(f"user not scoped to {incident_id}")
        return u

    # ---------------- membership/presence ----------------
    def join(self, user_id: str, incident_id: str,
             kind: RoomKind = RoomKind.INCIDENT) -> Room:
        u = self._check_user_incident(user_id, incident_id)
        room = self._room(incident_id, kind)
        role = u["role"]
        if role not in JOIN_RULES[kind]:
            raise ChatDenied(f"role {role.value} cannot join {kind.value}")
        room.members[user_id] = {"role": role.value,
                                 "connected": True,
                                 "last_seen": self.clock(),
                                 "last_read_seq": 0}
        return room

    def leave(self, user_id: str, incident_id: str,
              kind: RoomKind = RoomKind.INCIDENT) -> None:
        room = self._room(incident_id, kind)
        if user_id in room.members:
            room.members[user_id]["connected"] = False
            room.members[user_id]["last_seen"] = self.clock()

    def presence(self, incident_id: str,
                 kind: RoomKind = RoomKind.INCIDENT) -> list[dict]:
        room = self._room(incident_id, kind)
        return [{"user_id": uid, "role": m["role"],
                 "connected": m["connected"],
                 "last_seen": m["last_seen"]}
                for uid, m in room.members.items()]

    # ---------------- posting ----------------
    def post(self, user_id: str, incident_id: str, body: str,
             client_nonce: str = "",
             kind: RoomKind = RoomKind.INCIDENT,
             links: dict | None = None) -> tuple[Message, bool]:
        """Post a chat message. Returns (message, deduplicated).
        client_nonce dedups retries — same nonce returns original msg."""
        u = self._check_user_incident(user_id, incident_id)
        room = self._room(incident_id, kind)
        role = u["role"]
        if user_id not in room.members:
            raise ChatDenied("not a room member — join first")
        if role not in POST_RULES[kind]:
            raise ChatDenied(f"role {role.value} cannot post in {kind.value}")
        clean = sanitize(body)
        if not clean:
            raise ChatDenied("empty message after sanitization")
        # nonce dedup — retry returns original, no duplicate
        if client_nonce:
            key = f"{room.room_id}|{client_nonce}"
            if key in self._nonces:
                mid = self._nonces[key]
                orig = next(m for m in room.messages if m.msg_id == mid)
                return orig, True
        msg = Message(
            msg_id=f"msg-{uuid.uuid4().hex[:12]}", room_id=room.room_id,
            seq=len(room.messages) + 1, at=self.clock(),
            sender_id=user_id, sender_role=role, kind="chat",
            body=clean, client_nonce=client_nonce,
            links=links or {})
        room.messages.append(msg)
        if client_nonce:
            self._nonces[f"{room.room_id}|{client_nonce}"] = msg.msg_id
        # sender's own read cursor advances; others' unread grows
        room.members[user_id]["last_read_seq"] = msg.seq
        return msg, False

    def system_post(self, incident_id: str, text: str,
                    kind: RoomKind = RoomKind.INCIDENT,
                    links: dict | None = None) -> Message:
        """System message — agent missions, approval outcomes, verified
        containment. Posted by the service, links to action/evidence."""
        room = self._room(incident_id, kind)
        msg = Message(
            msg_id=f"sys-{uuid.uuid4().hex[:12]}", room_id=room.room_id,
            seq=len(room.messages) + 1, at=self.clock(),
            sender_id="system", sender_role=PrincipalRole.SYSTEM,
            kind="system", body=sanitize(text), links=links or {})
        room.messages.append(msg)
        return msg

    # ---------------- reads ----------------
    def history(self, incident_id: str, since_seq: int = 0,
                kind: RoomKind = RoomKind.INCIDENT) -> list[Message]:
        """Reconnect recovery: client supplies last seen seq, gets only
        newer messages — ordered, no duplicates."""
        room = self._room(incident_id, kind)
        return [m for m in room.messages if m.seq > since_seq]

    def unread_counts(self, incident_id: str,
                      kind: RoomKind = RoomKind.INCIDENT) -> dict[str, int]:
        room = self._room(incident_id, kind)
        return {uid: max(0, len(room.messages) - m["last_read_seq"])
                for uid, m in room.members.items()}

    def mark_read(self, user_id: str, incident_id: str,
                  up_to_seq: int,
                  kind: RoomKind = RoomKind.INCIDENT) -> None:
        room = self._room(incident_id, kind)
        if user_id in room.members:
            room.members[user_id]["last_read_seq"] = max(
                room.members[user_id]["last_read_seq"], up_to_seq)
