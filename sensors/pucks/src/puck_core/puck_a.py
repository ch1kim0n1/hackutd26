"""Puck A — ESP32-S3 2.4 GHz Wi-Fi scanner.

Emits wifi_ap_seen per AP per scan with known/unknown-BSSID classification
against the authorized inventory. Repeated unknown-BSSID-on-known-SSID is
surfaced as data.suspicion='unknown_bssid_on_known_ssid' — evidence, NOT
proof of an evil twin (docs/03)."""
from __future__ import annotations

from .models import EventKind
from .puck_base import PuckBase

DEDUP_WINDOW_S = 5.0  # identical AP report within window -> no duplicate event


class WifiPuck(PuckBase):
    puck_type = "puck-a"

    def __init__(self, *args, scan_channel_hop: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        self.scan_channel_hop = scan_channel_hop
        self._seen: dict[tuple[str, str, int], float] = {}
        self._unknown_streak: dict[str, int] = {}

    def scan(self, results: list[dict]) -> list:
        """results: [{ssid,bssid,channel,rssi_dbm}] -> emitted events."""
        now = self.clock()
        emitted = []
        for ap in results:
            ssid = str(ap.get("ssid", ""))
            bssid = str(ap.get("bssid", "")).lower()
            channel = int(ap.get("channel", 0))
            rssi = int(ap.get("rssi_dbm", -127))
            key = (ssid, bssid, channel)
            last = self._seen.get(key)
            if last is not None and now - last < DEDUP_WINDOW_S:
                continue
            self._seen[key] = now
            known = self.inventory.is_known_bssid(ssid, bssid)
            ssid_known = self.inventory.ssid_known(ssid)
            streak = self._unknown_streak.get(ssid, 0)
            if ssid_known and not known:
                streak += 1
                suspicion = "unknown_bssid_on_known_ssid" if streak >= 2 else "first_unknown_bssid"
            else:
                streak = 0
                suspicion = "none"
            self._unknown_streak[ssid] = streak
            obs = self.emit(EventKind.WIFI_AP_SEEN, {
                "ssid": ssid,
                "bssid": bssid,
                "channel": channel,
                "rssi_dbm": rssi,
                "source_id": self.device_id,
                "known_bssid": known,
                "ssid_known": ssid_known,
                "unknown_bssid_streak": streak,
                "suspicion": suspicion,
                "scan_channel_hop": self.scan_channel_hop,
            })
            emitted.append(obs)
        return emitted
