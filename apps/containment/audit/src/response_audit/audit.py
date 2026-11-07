"""Append-only, hash-chained audit log (docs/04 audit_events + docs/08
evidence provenance: 'append-only action log with actor, reason,
before/after state and verification result').

Each entry stores prev_hash; entry hash covers canonical content.
Tampering with any historical entry breaks the chain — detectable via
verify(). Hash-chaining flags edits to exported snapshots; it does NOT
make a compromised DB immutable (docs/08 caveat, documented)."""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

GENESIS = "0" * 64


def _canon(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


@dataclass
class AuditEntry:
    seq: int
    event_id: str
    at: str
    actor: str
    actor_role: str
    operation: str               # propose|approve|deny|execute|verify|revert|recover|note
    entity_type: str             # action|incident|approval|mission|evidence
    entity_id: str
    incident_id: str
    reason: str
    before: dict = field(default_factory=dict)
    after: dict = field(default_factory=dict)
    verification: dict = field(default_factory=dict)
    trace_id: str = ""
    prev_hash: str = GENESIS
    hash: str = ""

    def content(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if k != "hash"}


class AuditLog:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        self.entries: list[AuditEntry] = []
        self._last_hash = GENESIS
        if self.path and self.path.exists():
            self._load()

    # ---------------- write ----------------
    def append(self, *, actor: str, actor_role: str, operation: str,
               entity_type: str, entity_id: str, incident_id: str,
               reason: str = "", before: dict | None = None,
               after: dict | None = None, verification: dict | None = None,
               trace_id: str = "") -> AuditEntry:
        e = AuditEntry(
            seq=len(self.entries),
            event_id=f"aud-{uuid.uuid4().hex[:12]}",
            at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            actor=actor, actor_role=actor_role, operation=operation,
            entity_type=entity_type, entity_id=entity_id,
            incident_id=incident_id, reason=reason,
            before=before or {}, after=after or {},
            verification=verification or {}, trace_id=trace_id,
            prev_hash=self._last_hash)
        e.hash = hashlib.sha256(_canon(e.content())).hexdigest()
        self.entries.append(e)
        self._last_hash = e.hash
        self._persist(e)
        return e

    # ---------------- read ----------------
    def timeline(self, incident_id: str | None = None,
                 entity_id: str | None = None,
                 actor: str | None = None) -> list[AuditEntry]:
        out = self.entries
        if incident_id:
            out = [e for e in out if e.incident_id == incident_id]
        if entity_id:
            out = [e for e in out if e.entity_id == entity_id]
        if actor:
            out = [e for e in out if e.actor == actor]
        return out

    def operations_for(self, entity_id: str) -> list[str]:
        return [e.operation for e in self.timeline(entity_id=entity_id)]

    # ---------------- integrity ----------------
    def verify(self) -> tuple[bool, str]:
        """Recompute chain; returns (ok, failure_description)."""
        prev = GENESIS
        for i, e in enumerate(self.entries):
            if e.seq != i:
                return False, f"seq gap at index {i}"
            if e.prev_hash != prev:
                return False, f"prev_hash mismatch at seq {e.seq}"
            if e.hash != hashlib.sha256(_canon(e.content())).hexdigest():
                return False, f"content hash mismatch at seq {e.seq}"
            prev = e.hash
        return True, "chain intact"

    # ---------------- persistence ----------------
    def _persist(self, e: AuditEntry) -> None:
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a") as f:
                f.write(json.dumps(e.__dict__, sort_keys=True) + "\n")

    def _load(self) -> None:
        for line in self.path.read_text().splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            e = AuditEntry(**{k: v for k, v in d.items()
                              if k in AuditEntry.__dataclass_fields__})
            self.entries.append(e)
            self._last_hash = e.hash
