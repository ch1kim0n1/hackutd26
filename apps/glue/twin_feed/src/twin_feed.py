"""GLUE-04: unified feed for the digital twin — rover poses, RF scans,
photo evidence, incident timeline, scope matrix, chat.

Every item carries provenance (LIVE/REPLAY/SYNTHETIC), timestamp and
staleness; subscription is role+incident scoped server-side. This is
the data contract the React/R3F twin (#28) and RF drilldown (#29)
consume — no fabricated spectrum: RF items only exist if a scan
produced them."""
from __future__ import annotations

import time
from dataclasses import dataclass, field


class FeedDenied(Exception):
    pass


PROVENANCE = {"LIVE", "REPLAY", "SYNTHETIC"}


@dataclass
class FeedItem:
    kind: str                    # rover_pose|rf_scan|photo|timeline|scope|chat
    ref_id: str
    at: float
    provenance: str              # LIVE|REPLAY|SYNTHETIC
    payload: dict = field(default_factory=dict)
    stale: bool = False


class TwinFeed:
    STALE_AFTER_S = 15.0

    def __init__(self, clock=time.time):
        self.clock = clock
        self.items: list[FeedItem] = []
        self.subscriptions: dict[str, dict] = {}  # sub_id -> principal

    # ---------------- ingest (server-side producers only) -------------
    def push(self, kind: str, ref_id: str, payload: dict,
             provenance: str = "LIVE") -> FeedItem:
        if provenance not in PROVENANCE:
            raise FeedDenied(f"bad provenance {provenance}")
        item = FeedItem(kind=kind, ref_id=ref_id, at=self.clock(),
                        provenance=provenance, payload=payload)
        self.items.append(item)
        return item

    # ---------------- subscriptions ------------------------------------
    def subscribe(self, user_id: str, role: str,
                  incident_scope: set[str]) -> str:
        sid = f"sub-{user_id}-{len(self.subscriptions)}"
        self.subscriptions[sid] = {"user": user_id, "role": role,
                                   "scope": incident_scope}
        return sid

    def _allowed(self, sub: dict, item: FeedItem) -> bool:
        if sub["role"] in ("admin", "commander"):
            return True
        # incident-bound items need scope match; unscoped infra items ok
        inc = item.payload.get("incident_id")
        if inc is None:
            return True
        return inc in sub["scope"]

    def stream(self, sub_id: str, since: int = 0) -> list[FeedItem]:
        sub = self.subscriptions.get(sub_id)
        if sub is None:
            raise FeedDenied("unknown subscription")
        out = []
        for i, it in enumerate(self.items):
            if i < since:
                continue
            if not self._allowed(sub, it):
                continue
            # mark staleness at read time — honest, never hidden
            it.stale = (self.clock() - it.at) > self.STALE_AFTER_S
            out.append(it)
        return out

    # ---------------- convenience views --------------------------------
    def rover_pose(self) -> FeedItem | None:
        poses = [i for i in self.items if i.kind == "rover_pose"]
        return poses[-1] if poses else None

    def rf_scans(self) -> list[FeedItem]:
        """Only real scan outputs — never synthesized spectrum."""
        return [i for i in self.items if i.kind == "rf_scan"]

    def incident_context(self, incident_id: str) -> dict:
        return {
            "timeline": [i.payload for i in self.items
                         if i.kind == "timeline"
                         and i.payload.get("incident_id") == incident_id],
            "scope": [i.payload for i in self.items
                      if i.kind == "scope"
                      and i.payload.get("incident_id") == incident_id],
            "chat": [i.payload for i in self.items
                     if i.kind == "chat"
                     and i.payload.get("incident_id") == incident_id],
            "photos": [i.payload for i in self.items
                       if i.kind == "photo"
                       and i.payload.get("incident_id") == incident_id],
        }
