"""Authorized-fixture inventory: known APs, enrolled BLE beacons,
maintenance windows. Loaded from JSON; nothing here trusts the RF side."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MaintenanceWindow:
    zone_id: str
    start: str  # ISO-8601 UTC
    end: str
    authorized_by: str = "operator"

    def covers(self, zone_id: str, iso_ts: str) -> bool:
        return zone_id == self.zone_id and self.start <= iso_ts <= self.end


@dataclass
class Inventory:
    """What 'known' means for this deployment."""

    # ssid -> set of authorized BSSIDs (lowercase)
    known_bssids: dict[str, set[str]] = field(default_factory=dict)
    # enrolled BLE beacon keys: lowercase address OR service UUID
    enrolled_beacons: set[str] = field(default_factory=set)
    maintenance_windows: list[MaintenanceWindow] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict) -> "Inventory":
        return cls(
            known_bssids={
                str(ssid): {str(b).lower() for b in bssids}
                for ssid, bssids in raw.get("known_bssids", {}).items()
            },
            enrolled_beacons={str(b).lower() for b in raw.get("enrolled_beacons", [])},
            maintenance_windows=[
                MaintenanceWindow(str(w["zone_id"]), str(w["start"]), str(w["end"]),
                                  str(w.get("authorized_by", "operator")))
                for w in raw.get("maintenance_windows", [])
            ],
        )

    @classmethod
    def load(cls, path: str | Path) -> "Inventory":
        return cls.from_dict(json.loads(Path(path).read_text()))

    def is_known_bssid(self, ssid: str, bssid: str) -> bool:
        return bssid.lower() in self.known_bssids.get(ssid, set())

    def ssid_known(self, ssid: str) -> bool:
        return ssid in self.known_bssids

    def is_enrolled_beacon(self, address: str | None, service_uuid: str | None) -> bool:
        if address and address.lower() in self.enrolled_beacons:
            return True
        if service_uuid and service_uuid.lower() in self.enrolled_beacons:
            return True
        return False

    def maintenance_active(self, zone_id: str, iso_ts: str) -> bool:
        return any(w.covers(zone_id, iso_ts) for w in self.maintenance_windows)
