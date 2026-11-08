"""Wand <-> backend contract for POST /api/wand (issue #117).

NOTE: ``network_wand_code/backend/app.py`` does NOT exist — the production
backend endpoint is an unimplemented integration boundary (Team B scope).
This module freezes the wire contract that ``wand.py`` already speaks so
the boundary can be faked, tested, and later implemented without guesswork.

Request  (wand -> backend, every ``poll_seconds``):
    {wand_id, rack_id, bssid, rssi, mode, frames_per_s, deauths_3s, ack}
    mode ∈ {HUNT, MONITOR, SCAN, STATUS}; rssi may be null; ack is the
    wand's pending-alert flag the backend clears by responding.

Response (backend -> wand, JSON object, all fields optional):
    {bssid, rack_id, channel}
    A non-empty bssid different from the wand's current target retasks the
    wand; channel is the 2.4 GHz channel to hunt on.

``FakeWandBackend`` implements these semantics in-process for contract
tests and bench demos. It is NOT a server and performs no RF actions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

WAND_MODES = ("HUNT", "MONITOR", "SCAN", "STATUS")

REPORT_FIELDS = ("wand_id", "rack_id", "bssid", "rssi", "mode",
                 "frames_per_s", "deauths_3s", "ack")
COMMAND_FIELDS = ("bssid", "rack_id", "channel")


class ContractError(ValueError):
    pass


@dataclass
class WandCommand:
    """Backend -> wand retask instruction."""
    bssid: str = ""
    rack_id: str = ""
    channel: int = 0

    @classmethod
    def from_dict(cls, raw: dict) -> "WandCommand":
        if not isinstance(raw, dict):
            raise ContractError("wand command must be a JSON object")
        bssid = str(raw.get("bssid") or "").lower()
        rack_id = str(raw.get("rack_id") or "")
        try:
            channel = int(raw.get("channel") or 0)
        except (TypeError, ValueError):
            raise ContractError("channel must be an integer")
        if channel and not (1 <= channel <= 14):
            raise ContractError("channel out of 2.4GHz range")
        return cls(bssid=bssid, rack_id=rack_id, channel=channel)


@dataclass
class WandReport:
    """Wand -> backend telemetry/ack report."""
    wand_id: str
    rack_id: str
    bssid: str
    rssi: Optional[float]
    mode: str
    frames_per_s: float
    deauths_3s: int
    ack: bool

    @classmethod
    def from_dict(cls, raw: dict) -> "WandReport":
        if not isinstance(raw, dict):
            raise ContractError("wand report must be a JSON object")
        missing = [f for f in REPORT_FIELDS if f not in raw]
        if missing:
            raise ContractError(f"missing fields: {','.join(missing)}")
        mode = str(raw["mode"])
        if mode not in WAND_MODES:
            raise ContractError(f"unknown mode {mode!r}")
        try:
            rssi = raw["rssi"]
            rssi = None if rssi is None else float(rssi)
            fps = float(raw["frames_per_s"])
            deauths = int(raw["deauths_3s"])
        except (TypeError, ValueError):
            raise ContractError("rssi/frames_per_s/deauths_3s must be numeric")
        return cls(
            wand_id=str(raw["wand_id"]), rack_id=str(raw["rack_id"] or ""),
            bssid=str(raw["bssid"] or "").lower(), rssi=rssi, mode=mode,
            frames_per_s=fps, deauths_3s=deauths, ack=bool(raw["ack"]),
        )

    def to_dict(self) -> dict:
        return {
            "wand_id": self.wand_id, "rack_id": self.rack_id,
            "bssid": self.bssid, "rssi": self.rssi, "mode": self.mode,
            "frames_per_s": self.frames_per_s, "deauths_3s": self.deauths_3s,
            "ack": self.ack,
        }


@dataclass
class FakeWandBackend:
    """In-process /api/wand double.

    Mirrors the semantics wand.py depends on:
      - responds with the current commanded target {bssid, rack_id, channel}
      - a report with ack=True clears the pending alert
      - set_target() retasks all wands on their next poll
    """
    target: WandCommand = field(default_factory=WandCommand)
    reports: list[WandReport] = field(default_factory=list)
    acks_cleared: int = 0

    def set_target(self, bssid: str, rack_id: str = "", channel: int = 0) -> WandCommand:
        self.target = WandCommand.from_dict(
            {"bssid": bssid, "rack_id": rack_id, "channel": channel})
        return self.target

    def handle(self, raw: dict) -> dict:
        """One POST /api/wand round-trip -> response body dict."""
        report = WandReport.from_dict(raw)
        self.reports.append(report)
        if report.ack:
            self.acks_cleared += 1
        return {
            "bssid": self.target.bssid,
            "rack_id": self.target.rack_id,
            "channel": self.target.channel,
        }
