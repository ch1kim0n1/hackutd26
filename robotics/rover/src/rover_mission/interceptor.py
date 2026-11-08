"""Wi-Fi interceptor: passive monitor-mode capture -> canonical observations.

Runs on the rover's monitor-mode adapter (see network_wand_code/monmode.sh).
Emits wifi_ap_seen / wifi_probe / ble_beacon_seen style envelopes over the
existing Publisher (MQTT -> gateway -> ingestObservation). scapy is an
optional dependency; pure helpers below are unit-testable without it.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from typing import Callable, Optional

SCHEMA_VERSION = 1

# 802.11 management subtype -> observation kind (canonical vocabulary,
# must stay in sync with spacetimedb OBSERVATION_KINDS + puck kinds).
_FRAME_KIND = {
    0x00: "rf_frame_meta",       # assoc request
    0x04: "wifi_probe",          # probe request -> client hunting an SSID
    0x05: "wifi_ap_seen",        # probe response (BSSID + SSID visible)
    0x08: "wifi_ap_seen",        # beacon -> AP seen
    0x0B: "rf_frame_meta",       # auth frame (rogue handshake attempt)
    0x0C: "rf_frame_meta",       # assoc response
    0x0D: "rf_frame_meta",       # reassoc request
    0x0E: "rf_frame_meta",       # reassoc response
    0x1C: "rf_frame_meta",       # action frames (WPS, PMF negotiation)
}


def classify_frame(subtype: int) -> Optional[str]:
    """Map an 802.11 mgmt subtype nibble to an observation kind."""
    return _FRAME_KIND.get(subtype & 0x0F)


def mac_str(raw: bytes) -> str:
    return ":".join(f"{b:02x}" for b in raw)


def ssid_from_tags(tags: bytes) -> str:
    """Extract SSID from raw tagged parameters (element id 0)."""
    i = 0
    while i + 2 <= len(tags):
        elem_id, length = tags[i], tags[i + 1]
        if elem_id == 0:
            raw = tags[i + 2 : i + 2 + length]
            try:
                return raw.decode("utf-8", errors="replace")
            except Exception:
                return ""
        i += 2 + length
    return ""


def build_observation(
    device_id: str,
    zone_id: str,
    kind: str,
    data: dict,
    seq: int,
    secret: bytes = b"",
) -> dict:
    """Canonical signed observation envelope (same shape as puck_core)."""
    from datetime import datetime, timezone

    obs = {
        "schema_version": SCHEMA_VERSION,
        "event_id": f"evt-{uuid.uuid4().hex[:12]}",
        "device_id": device_id,
        "seq": seq,
        "observed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "kind": kind,
        "zone_id": zone_id,
        "data": data,
    }
    if secret:
        import hashlib
        import hmac as _hmac

        body = json.dumps(
            {k: obs[k] for k in ("schema_version", "event_id", "device_id", "seq",
                                 "observed_at", "kind", "zone_id", "data")},
            sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        )
        obs["signature"] = _hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()
    return obs


class Interceptor:
    """Monitor-mode frame sniffer -> Publisher. scapy required at runtime."""

    def __init__(
        self,
        device_id: str,
        zone_id: str,
        publisher,
        iface: str = "wlan1",
        channel: int = 6,
        secret: bytes = b"",
        on_frame: Optional[Callable[[dict], None]] = None,
    ):
        self.device_id = device_id
        self.zone_id = zone_id
        self.publisher = publisher
        self.iface = iface
        self.channel = channel
        self.secret = secret
        self._seq = 0
        self._seen: dict[str, float] = {}
        self.on_frame = on_frame
        self._dedupe_window_s = 5.0

    def _should_emit(self, key: str) -> bool:
        now = time.time()
        if now - self._seen.get(key, 0) < self._dedupe_window_s:
            return False
        self._seen[key] = now
        # bound memory: drop expired entries occasionally
        if len(self._seen) > 4096:
            cutoff = now - self._dedupe_window_s * 2
            self._seen = {k: v for k, v in self._seen.items() if v > cutoff}
        return True

    def handle_packet(self, pkt) -> None:
        """Extract observation from a scapy Dot11 packet; publish if new."""
        try:
            from scapy.layers.dot11 import Dot11, Dot11Beacon, Dot11ProbeResp, Dot11Elt
        except ImportError:
            raise RuntimeError("scapy not installed: pip install scapy")

        if not isinstance(pkt, Dot11):
            return
        fc = pkt.FCfield
        subtype = int(fc.subtype)
        kind = classify_frame(subtype)
        if kind is None:
            return

        addr1 = mac_str(pkt.addr1) if pkt.addr1 else ""
        addr2 = mac_str(pkt.addr2) if pkt.addr2 else ""
        addr3 = mac_str(pkt.addr3) if pkt.addr3 else ""
        data: dict = {
            "frame_subtype": subtype,
            "addr1": addr1, "addr2": addr2, "addr3": addr3,
            "rssi_dbm": int(getattr(pkt, "dBm_AntSignal", -100) or -100),
            "channel": self.channel,
        }
        ssid = ""
        for elt in pkt.iterpayloads():
            if isinstance(elt, Dot11Elt) and elt.ID == 0:
                ssid = elt.info.decode("utf-8", errors="replace") if elt.info else ""
                break
        if ssid:
            data["ssid"] = ssid
        if isinstance(pkt, (Dot11Beacon, Dot11ProbeResp)):
            data["bssid"] = addr3 or addr2
        elif subtype in (0x04, 0x05):  # probe req/resp
            data["probe_target"] = ssid or addr3

        # dedupe per (kind, bssid/addr2, ssid) so beacon floods don't spam
        key = f"{kind}:{data.get('bssid') or addr2}:{ssid}"
        if not self._should_emit(key):
            return

        self._seq += 1
        obs = build_observation(
            self.device_id, self.zone_id, kind, data, self._seq, self.secret
        )
        self.publisher.publish(obs)
        if self.on_frame:
            self.on_frame(obs)

    def run_forever(self, sniff_kwargs: Optional[dict] = None) -> None:
        """Blocking sniff loop (scapy). Call from CLI or a thread."""
        from scapy.all import sniff

        kwargs = {"iface": self.iface, "prn": self.handle_packet,
                  "store": False, "monitor": True}
        kwargs.update(sniff_kwargs or {})
        sniff(**kwargs)
