"""Authorized-fixture inventory for correlation (known BSSIDs etc.)."""
from __future__ import annotations

import json
from pathlib import Path


class Inventory:
    def __init__(self, known_bssids: dict[str, set[str]] | None = None):
        self.known_bssids = {
            ssid: {b.lower() for b in v}
            for ssid, v in (known_bssids or {}).items()
        }

    @classmethod
    def load(cls, path: str | Path) -> "Inventory":
        raw = json.loads(Path(path).read_text())
        return cls({s: set(v) for s, v in raw.get("known_bssids", {}).items()})

    def is_known(self, ssid: str, bssid: str) -> bool:
        return bssid.lower() in self.known_bssids.get(ssid, set())
