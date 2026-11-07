"""Normalized observation + alert/incident-candidate models."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

CORR_WINDOW_S = 120.0  # docs/03 CORR01 window


class Source(str, Enum):
    KISMET = "kismet"
    ESP32_PUCK = "esp32_puck"
    ROVER = "rover"
    GATEWAY = "gateway"


class NormKind(str, Enum):
    WIFI_AP_SEEN = "wifi_ap_seen"
    CABINET_CONTACT_OPEN = "cabinet_contact_open"
    CABINET_CONTACT_CLOSED = "cabinet_contact_closed"
    BLE_BEACON_SEEN = "ble_beacon_seen"
    OTHER = "other"


@dataclass
class NormalizedObservation:
    """Adapter output — one shape regardless of capture source."""
    source: Source
    receiver_id: str
    observed_at: str          # ISO-8601 UTC
    observed_epoch: float
    kind: NormKind
    zone_id: str
    event_id: str = field(default_factory=lambda: f"obs-{uuid.uuid4().hex[:12]}")
    data: dict[str, Any] = field(default_factory=dict)
    raw_ref: str = ""         # pointer to raw artifact (kismetdb line etc.)

    @property
    def dedup_key(self) -> str:
        if self.kind == NormKind.WIFI_AP_SEEN:
            return f"wifi|{self.zone_id}|{self.data.get('ssid','')}|{self.data.get('bssid','')}"
        if self.kind in (NormKind.CABINET_CONTACT_OPEN, NormKind.CABINET_CONTACT_CLOSED):
            return f"cab|{self.zone_id}|{self.data.get('contact','')}"
        if self.kind == NormKind.BLE_BEACON_SEEN:
            return f"ble|{self.zone_id}|{self.data.get('beacon_key','')}"
        return f"{self.kind.value}|{self.receiver_id}|{self.observed_epoch}"


@dataclass
class Alert:
    rule_id: str               # RF01 | PHY01 | CORR01 | NET01
    severity: str              # info | low | medium | high
    state: str                 # candidate | suppressed | confirmed
    zone_id: str
    observation_ids: list[str]
    summary: str
    evidence_quality: dict[str, Any] = field(default_factory=dict)
    fired_at_epoch: float = field(default_factory=time.time)


@dataclass
class IncidentCandidate:
    """CORR01 output — a *candidate*, not a confirmed breach."""
    title: str
    zone_id: str
    alert_ids: list[str]
    evidence: list[str]        # observation ids
    confidence: str            # evidence-quality label, not model certainty
    alternatives: list[str]
    unknowns: list[str]
    created_epoch: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "title": self.title, "zone_id": self.zone_id,
            "alert_ids": self.alert_ids, "evidence": self.evidence,
            "confidence": self.confidence, "alternatives": self.alternatives,
            "unknowns": self.unknowns,
        }
