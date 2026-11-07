"""P0 fallback: Wi-Fi channel activity view from wifi_ap_seen observations.
Explicitly NOT a spectrum waterfall (docs/03)."""
from __future__ import annotations

import time
from collections import defaultdict

from .models import ChannelActivity, SourceMode


def channel_activity(observations: list[dict], zone_id: str,
                     source_mode: SourceMode = SourceMode.LIVE
                     ) -> ChannelActivity:
    """observations: list of canonical wifi_ap_seen event dicts."""
    channels: dict[int, dict] = defaultdict(
        lambda: {"ap_count": 0, "rssi_dbm": [], "ssids": set()})
    ap_keys = set()
    for ob in observations:
        if ob.get("kind") != "wifi_ap_seen":
            continue
        d = ob.get("data", {})
        ch = int(d.get("channel", 0))
        if not ch:
            continue
        bssid = str(d.get("bssid", "")).lower()
        ap_keys.add((ch, bssid))
        channels[ch]["ap_count"] += 1
        if "rssi_dbm" in d:
            channels[ch]["rssi_dbm"].append(int(d["rssi_dbm"]))
        if d.get("ssid"):
            channels[ch]["ssids"].add(str(d["ssid"]))
    out = {}
    for ch, v in channels.items():
        rssis = v["rssi_dbm"]
        out[ch] = {
            "observation_count": v["ap_count"],
            "unique_bssids": len({k[1] for k in ap_keys if k[0] == ch}),
            "ssids": sorted(v["ssids"]),
            "rssi_dbm_min": min(rssis) if rssis else None,
            "rssi_dbm_max": max(rssis) if rssis else None,
            "rssi_dbm_mean": round(sum(rssis) / len(rssis), 1) if rssis else None,
        }
    return ChannelActivity(
        zone_id=zone_id,
        generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        source_mode=source_mode,
        channels=out,
        ap_count=len(ap_keys),
    )
