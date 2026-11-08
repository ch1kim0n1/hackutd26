"""Append-only, hash-chained flow-decision log — issue #105.

Mirrors apps/containment/audit/audit.py: every record carries seq,
record_id, UTC recorded_at, the full decision contract record,
trace_id, prev_hash and hash. verify() recomputes the chain so any
historical edit is detectable. Optional JSONL persistence + reload.

This log records POLICY OUTCOMES (decisions). It is not an enforcement
log — enforcement="simulated" is inside every stored record by
contract; real enforcement evidence arrives via #106+.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import FlowDecision

GENESIS = "0" * 64


def _canon(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


@dataclass
class DecisionRecord:
    seq: int
    record_id: str
    recorded_at: str
    decision: dict          # FlowDecision.as_record()
    trace_id: str
    prev_hash: str = GENESIS
    hash: str = ""

    def content(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if k != "hash"}

    # convenience projections over the nested decision record
    @property
    def flow_id(self) -> str:
        return self.decision["flow"]["flow_id"]

    @property
    def outcome(self) -> str:
        return self.decision["decision"]

    @property
    def policy_id(self) -> str:
        return self.decision["policy_id"]


class DecisionLog:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        self.records_list: list[DecisionRecord] = []
        self._last_hash = GENESIS
        if self.path and self.path.exists():
            self._load()

    # ---------------- write ----------------
    def append(self, decision: FlowDecision,
               *, recorded_at: str | None = None) -> DecisionRecord:
        if not isinstance(decision, FlowDecision):
            raise TypeError("append() requires a FlowDecision")
        rec = DecisionRecord(
            seq=len(self.records_list),
            record_id=f"dlog-{uuid.uuid4().hex[:12]}",
            recorded_at=recorded_at or time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            decision=decision.as_record(),
            trace_id=decision.trace_id,
            prev_hash=self._last_hash)
        rec.hash = hashlib.sha256(_canon(rec.content())).hexdigest()
        self.records_list.append(rec)
        self._last_hash = rec.hash
        self._persist(rec)
        return rec

    # ---------------- read ----------------
    def records(self, *, flow_id: str | None = None,
                outcome: str | None = None,
                policy_id: str | None = None) -> list[DecisionRecord]:
        out = self.records_list
        if flow_id:
            out = [r for r in out if r.flow_id == flow_id]
        if outcome:
            out = [r for r in out if r.outcome == outcome]
        if policy_id:
            out = [r for r in out if r.policy_id == policy_id]
        return out

    # ---------------- integrity ----------------
    def verify(self) -> tuple[bool, str]:
        """Recompute chain; returns (ok, failure_description)."""
        prev = GENESIS
        for i, r in enumerate(self.records_list):
            if r.seq != i:
                return False, f"seq gap at index {i}"
            if r.prev_hash != prev:
                return False, f"prev_hash mismatch at seq {r.seq}"
            if r.hash != hashlib.sha256(_canon(r.content())).hexdigest():
                return False, f"content hash mismatch at seq {r.seq}"
            prev = r.hash
        return True, "chain intact"

    # ---------------- persistence ----------------
    def _persist(self, r: DecisionRecord) -> None:
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a") as f:
                f.write(json.dumps(r.__dict__, sort_keys=True) + "\n")

    def _load(self) -> None:
        for line in self.path.read_text().splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            rec = DecisionRecord(
                seq=d["seq"], record_id=d["record_id"],
                recorded_at=d["recorded_at"], decision=d["decision"],
                trace_id=d.get("trace_id", ""),
                prev_hash=d.get("prev_hash", GENESIS),
                hash=d.get("hash", ""))
            self.records_list.append(rec)
            self._last_hash = rec.hash
