"""UX-29: RF channel intelligence + evidence drilldown data layer.

Builds channel heatmap, BSSID inventory, RSSI time series strictly
from real scan outputs — LIVE/REPLAY provenance enforced, permission-
checked evidence refs, timestamps on everything. No unmeasured
spectral claims: only channels/BSSIDs actually observed appear."""
from __future__ import annotations

import time
from collections import defaultdict


class RFIntelDenied(Exception):
    pass


class RFIntel:
    def __init__(self, clock=time.time):
        self.clock = clock
        self.scans: list[dict] = []   # {at, provenance, source, aps:[{bssid,ssid,channel,rssi}]}
        self.incident_links: dict[str, str] = {}  # bssid -> incident_id

    # ---------------- ingest ------------------------------------------
    def add_scan(self, source: str, aps: list[dict],
                 provenance: str = "LIVE") -> dict:
        if provenance not in ("LIVE", "REPLAY"):
            raise RFIntelDenied("provenance must be LIVE or REPLAY")
        scan = {"at": self.clock(), "source": source,
                "provenance": provenance, "aps": aps}
        self.scans.append(scan)
        return scan

    # ---------------- channel heatmap ----------------------------------
    def channel_heatmap(self) -> dict[int, dict]:
        """channel -> {count, avg_rssi, bssids, last_seen, provenance}.
        Only observed channels — no fabricated spectrum."""
        heat: dict[int, dict] = defaultdict(
            lambda: {"count": 0, "rssi_sum": 0, "bssids": set(),
                     "last_seen": 0.0, "provenance": set()})
        for s in self.scans:
            for ap in s["aps"]:
                ch = ap.get("channel")
                if ch is None:
                    continue
                h = heat[ch]
                h["count"] += 1
                h["rssi_sum"] += ap.get("rssi_dbm", -100)
                h["bssids"].add(ap.get("bssid", "?"))
                h["last_seen"] = max(h["last_seen"], s["at"])
                h["provenance"].add(s["provenance"])
        return {ch: {"count": h["count"],
                     "avg_rssi_dbm": round(h["rssi_sum"] / h["count"], 1),
                     "bssid_count": len(h["bssids"]),
                     "bssids": sorted(h["bssids"]),
                     "last_seen": h["last_seen"],
                     "provenance": sorted(h["provenance"]),
                     "age_s": round(self.clock() - h["last_seen"], 1)}
                for ch, h in sorted(heat.items())}

    # ---------------- BSSID inventory ----------------------------------
    def bssid_inventory(self) -> dict[str, dict]:
        inv: dict[str, dict] = {}
        for s in self.scans:
            for ap in s["aps"]:
                b = ap.get("bssid")
                if not b:
                    continue
                e = inv.setdefault(b, {"ssid": ap.get("ssid", "?"),
                                       "channels": set(), "rssi": [],
                                       "first_seen": s["at"],
                                       "last_seen": s["at"],
                                       "sources": set(),
                                       "provenance": set()})
                e["channels"].add(ap.get("channel"))
                e["rssi"].append(ap.get("rssi_dbm", -100))
                e["last_seen"] = max(e["last_seen"], s["at"])
                e["sources"].add(s["source"])
                e["provenance"].add(s["provenance"])
        return {b: {"ssid": e["ssid"],
                    "channels": sorted(e["channels"]),
                    "avg_rssi_dbm": round(sum(e["rssi"]) / len(e["rssi"]), 1),
                    "sightings": len(e["rssi"]),
                    "first_seen": e["first_seen"],
                    "last_seen": e["last_seen"],
                    "sources": sorted(e["sources"]),
                    "provenance": sorted(e["provenance"])}
                for b, e in sorted(inv.items())}

    # ---------------- RSSI over time (per BSSID/channel) ----------------
    def rssi_series(self, bssid: str | None = None,
                    channel: int | None = None) -> list[dict]:
        pts = []
        for s in self.scans:
            for ap in s["aps"]:
                if bssid and ap.get("bssid") != bssid:
                    continue
                if channel is not None and ap.get("channel") != channel:
                    continue
                pts.append({"at": s["at"], "bssid": ap.get("bssid"),
                            "ssid": ap.get("ssid"),
                            "channel": ap.get("channel"),
                            "rssi_dbm": ap.get("rssi_dbm"),
                            "provenance": s["provenance"],
                            "source": s["source"]})
        return pts

    # ---------------- evidence drilldown --------------------------------
    def evidence_for(self, bssid: str, role: str,
                     incident_scope: set[str]) -> dict:
        """Permission-checked: caller must have evidence read + the
        BSSID's linked incident must be in scope."""
        if role not in ("admin", "commander", "responder", "observer"):
            raise RFIntelDenied(f"role {role} cannot read evidence")
        inv = self.bssid_inventory()
        if bssid not in inv:
            raise RFIntelDenied("unknown bssid")
        linked = self.incident_links.get(bssid)
        if linked and linked not in incident_scope and \
                role not in ("admin", "commander"):
            raise RFIntelDenied("outside incident scope")
        return {"bssid": bssid, "inventory": inv[bssid],
                "series": self.rssi_series(bssid=bssid),
                "scans": len(self.scans)}
