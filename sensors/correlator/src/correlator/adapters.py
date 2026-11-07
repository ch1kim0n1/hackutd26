"""Input adapters: canonical puck events (docs/04), Kismet records,
raw ESP32 serial lines -> NormalizedObservation.

Kismet: accepts the dot11 fields kismetdb JSON-lines actually carry
(kismet.device.base.*, dot11.*). Tolerant extraction; unknown fields
ignored. No third-party capture is performed here — this only reads
ALREADY-COLLECTED authorized captures (docs/03, charter exclusions)."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from .models import NormKind, NormalizedObservation, Source


def _epoch(iso: str) -> float:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except Exception:
        return time.time()


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def adapt_puck_event(raw: dict[str, Any], zone_id: str | None = None) -> NormalizedObservation | None:
    """docs/04 canonical event (already HMAC-verified upstream by collector)."""
    kind = raw.get("kind", "")
    mapping = {
        "wifi_ap_seen": NormKind.WIFI_AP_SEEN,
        "cabinet_contact_open": NormKind.CABINET_CONTACT_OPEN,
        "cabinet_contact_closed": NormKind.CABINET_CONTACT_CLOSED,
        "ble_beacon_seen": NormKind.BLE_BEACON_SEEN,
    }
    if kind not in mapping:
        return None
    ts = raw.get("observed_at", "")
    ep = _epoch(ts) if ts else time.time()
    return NormalizedObservation(
        source=Source.ESP32_PUCK,
        receiver_id=str(raw.get("device_id", "unknown")),
        observed_at=ts or _iso(ep),
        observed_epoch=ep,
        kind=mapping[kind],
        zone_id=zone_id or str(raw.get("zone_id", "")),
        event_id=str(raw.get("event_id", "")),
        data=dict(raw.get("data", {})),
    )


def adapt_kismet_record(raw: dict[str, Any], zone_id: str,
                        receiver_id: str = "kismet-01") -> NormalizedObservation | None:
    """One kismetdb JSON device record -> wifi_ap_seen observation."""
    base = raw.get("kismet.device.base", {})
    dot11 = raw.get("kismet.device.base.dot11.device", {}) or \
            raw.get("kismet.device.base.dot11.advertisedssid", {})
    bssid = base.get("mac") or dot11.get("dot11.device")
    ssid = dot11.get("dot11.advertisedssid.ssid") or \
           dot11.get("dot11.device") or dot11.get("dot11.advertisedssid")
    channel = dot11.get("dot11.channel") or dot11.get("channel")
    rssi = dot11.get("dot11.signal") or dot11.get("signal") or dot11.get("rssi")
    ts = base.get("last_beaconed_time") or base.get("first_time")
    try:
        ep = float(ts)
    except (TypeError, ValueError):
        ep = time.time()
    if not bssid:
        return None
    return NormalizedObservation(
        source=Source.KISMET,
        receiver_id=receiver_id,
        observed_at=_iso(ep),
        observed_epoch=ep,
        kind=NormKind.WIFI_AP_SEEN,
        zone_id=zone_id,
        event_id=f"kst-{base.get('kismet.device.base.bssid', bssid)}-{int(ep)}",
        data={
            "ssid": str(ssid or ""),
            "bssid": str(bssid).lower(),
            "channel": int(channel) if channel is not None else 0,
            "rssi_dbm": int(rssi) if rssi is not None else -127,
            "source_id": receiver_id,
        },
        raw_ref="kismetdb",
    )


def adapt_stream(lines: list[str], zone_id: str,
                 receiver_id: str = "kismet-01") -> list[NormalizedObservation]:
    """Parse newline-delimited kismetdb JSON into observations."""
    out = []
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        obs = adapt_kismet_record(rec, zone_id, receiver_id)
        if obs:
            obs.raw_ref = f"kismetdb:line{i}"
            out.append(obs)
    return out
