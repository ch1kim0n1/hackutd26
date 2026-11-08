"""Honeypot AP: advertise decoy SSIDs to lure rogue clients, then flag
their probe/auth frames as hostile telemetry.

Two deployment modes:
  - 'beacon': scapy injects forged beacons/probe-responses on the monitor
    interface (no association needed, works on same radio)
  - 'ap': real AP via hostapd config emitted for the ESP32/Linux side

Rogue detection heuristic: a station that probes for or associates with a
honeypot SSID is by definition unauthorized (nobody legit knows it).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional

DEFAULT_DECOYS = [
    {"ssid": "FREE-AIRPORT-WIFI", "bssid": "02:11:22:33:44:55"},
    {"ssid": "GUEST-NO-PASSWORD", "bssid": "02:11:22:33:44:56"},
]


@dataclass
class RogueHit:
    mac: str
    ssid: str
    bssid: str
    first_seen: float
    frame_count: int = 1
    last_rssi: Optional[int] = None


class Honeypot:
    """Track stations interacting with decoy SSIDs."""

    def __init__(
        self,
        decoys: Optional[list[dict]] = None,
        on_rogue: Optional[Callable[[RogueHit], None]] = None,
        report_every_hits: int = 3,
    ):
        self.decoys = decoys or DEFAULT_DECOYS
        self.decoy_ssids = {d["ssid"] for d in self.decoys}
        self.bssid_to_ssid = {d["bssid"]: d["ssid"] for d in self.decoys}
        self.on_rogue = on_rogue
        self.report_every_hits = report_every_hits
        self.rogues: dict[str, RogueHit] = {}
        self._pending_report: dict[str, int] = {}

    def feed_observation(self, obs: dict) -> Optional[RogueHit]:
        """Inspect an outgoing observation; return RogueHit on new rogue."""
        data = obs.get("data", {})
        ssid = data.get("ssid") or data.get("probe_target") or ""
        bssid = data.get("bssid") or ""
        kind = obs.get("kind")

        # Case 1: station probes for our decoy SSID -> interested rogue
        # Case 2: frame FROM a decoy BSSID isn't rogue (we sent it).
        # Case 3: station associates/auths to decoy BSSID -> confirmed rogue.
        hit = None
        if ssid in self.decoy_ssids and kind in ("wifi_probe", "rf_frame_meta"):
            addr2 = data.get("addr2") or data.get("addr1") or ""
            if addr2:
                hit = self._record(addr2, ssid, bssid or self._decoy_bssid(ssid),
                                   data.get("rssi_dbm"))
        elif bssid in self.bssid_to_ssid and kind in ("rf_frame_meta",):
            # auth/assoc TO our decoy BSSID: addr2 is the station = rogue
            addr2 = data.get("addr2") or ""
            if addr2:
                hit = self._record(addr2, self.bssid_to_ssid[bssid], bssid,
                                   data.get("rssi_dbm"))
        return hit

    def _decoy_bssid(self, ssid: str) -> str:
        for d in self.decoys:
            if d["ssid"] == ssid:
                return d["bssid"]
        return ""

    def _record(self, mac: str, ssid: str, bssid: str, rssi) -> Optional[RogueHit]:
        now = time.time()
        hit = self.rogues.get(mac)
        if hit is None:
            hit = RogueHit(mac=mac, ssid=ssid, bssid=bssid, first_seen=now,
                           last_rssi=rssi)
            self.rogues[mac] = hit
            self._pending_report[mac] = 0
        else:
            hit.frame_count += 1
            hit.last_rssi = rssi
            hit.last_frame_at = now  # type: ignore[attr-defined]
        self._pending_report[mac] = self._pending_report.get(mac, 0) + 1
        if self.on_rogue and (
            self._pending_report[mac] >= self.report_every_hits
            or hit.frame_count == 1
        ):
            self._pending_report[mac] = 0
            self.on_rogue(hit)
        return hit


# ---------------------------------------------------------------------------
# Beacon injector (scapy). Forges probe-responses/beacons for decoy SSIDs so
# client devices "see" the honeypot AP. Requires monitor-mode iface.
# ---------------------------------------------------------------------------

def beacon_frames(decoys: list[dict], iface: str, channel: int = 6):
    """Yield scapy Dot11Beacon/Dot11ProbeResp frames advertising decoys."""
    try:
        from scapy.all import Dot11, Dot11Beacon, Dot11Elt, RadioTap, sendp
    except ImportError:
        raise RuntimeError("scapy not installed: pip install scapy")

    frames = []
    for d in decoys:
        ssid = d["ssid"].encode()
        bssid = d.get("bssid", "02:11:22:33:44:55")
        # beacon: AP -> broadcast
        frames.append(RadioTap() / Dot11(addr1="ff:ff:ff:ff:ff:ff",
                                         addr2=bssid, addr3=bssid)
                      / Dot11Beacon() / Dot11Elt(ID="SSID", info=ssid))
        # probe response: answers directed probes
        frames.append(RadioTap() / Dot11(addr1="ff:ff:ff:ff:ff:ff",
                                         addr2=bssid, addr3=bssid)
                      / Dot11ProbeResp() / Dot11Elt(ID="SSID", info=ssid))
    return frames, sendp


def hostapd_config(decoys: list[dict], iface: str = "wlan1",
                   channel: int = 6, hw_mode: str = "g") -> str:
    """Generate a multi-SSID hostapd config for real-AP honeypot mode."""
    lines = [
        f"interface={iface}",
        f"driver=nl80211",
        f"ssid=MERIDIAN-HONEYPOT",
        f"hw_mode={hw_mode}",
        f"channel={channel}",
        "ieee80211n=1",
        "wmm_enabled=1",
        # open network on purpose: lure must be zero-friction
        "auth_algs=1",
        "wpa=0",
    ]
    for i, d in enumerate(decoys):
        lines += [
            f"bss={iface}-honeypot-{i}",
            f"ssid={d['ssid']}",
            f"hw_mode={hw_mode}",
            f"channel={channel}",
            "auth_algs=1",
            "wpa=0",
        ]
    return "\n".join(lines) + "\n"
