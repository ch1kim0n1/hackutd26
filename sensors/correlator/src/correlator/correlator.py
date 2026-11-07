"""RF01/PHY01/CORR01 correlation engine (docs/03).

RF01: known SSID + unexpected BSSID observed in >=2 distinct scans.
PHY01: cabinet contact opens outside a maintenance window (authorized=false).
CORR01: an RF01 candidate and a PHY01 alert in the same zone within 120s
        -> incident candidate for rover inspection. NOT proof of breach.

All outputs carry evidence-quality notes, alternatives and unknowns —
confidence describes evidence, never model certainty (docs/03)."""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field

from .dedup import Deduplicator
from .inventory import Inventory
from .models import (
    CORR_WINDOW_S,
    Alert,
    IncidentCandidate,
    NormKind,
    NormalizedObservation,
)

RF01_MIN_SCANS = 2
ALERT_COOLDOWN_S = 300.0  # don't re-fire same rule+key within 5 min


@dataclass
class _RfTrack:
    ssid: str
    bssid: str
    zone_id: str
    scan_count: int = 0
    obs_ids: list[str] = field(default_factory=list)
    sources: set = field(default_factory=set)


@dataclass
class _PhyTrack:
    zone_id: str
    obs_ids: list[str] = field(default_factory=list)
    epoch: float = 0.0
    authorized: bool = False


class Correlator:
    def __init__(self, inventory: Inventory | None = None,
                 dedup_window_s: float = 30.0,
                 corr_window_s: float = CORR_WINDOW_S):
        self.inventory = inventory or Inventory()
        self.dedup = Deduplicator(dedup_window_s)
        self.corr_window_s = corr_window_s
        self._rf: dict[tuple[str, str, str], _RfTrack] = {}   # (zone,ssid,bssid)
        self._phy: list[_PhyTrack] = []
        self._fired: dict[str, float] = {}                    # cooldown keys
        self.alerts: list[Alert] = []
        self.incidents: list[IncidentCandidate] = []
        self.dedup_stats = {"total": 0, "duplicates": 0}

    # ---------------- ingest ----------------
    def ingest(self, obs: NormalizedObservation) -> list[Alert]:
        """Returns alerts fired by this observation (possibly empty)."""
        self.dedup_stats["total"] += 1
        is_dup, _ids = self.dedup.feed(obs)
        if is_dup:
            self.dedup_stats["duplicates"] += 1
        alerts: list[Alert] = []
        if obs.kind == NormKind.WIFI_AP_SEEN:
            a = self._eval_wifi(obs)
            if a:
                alerts.append(a)
        elif obs.kind == NormKind.CABINET_CONTACT_OPEN:
            a = self._eval_cabinet(obs)
            if a:
                alerts.append(a)
                alerts.extend(self._eval_corr(a))
        elif obs.kind == NormKind.CABINET_CONTACT_CLOSED:
            # close resolves an open PHY track but is itself not an alert
            self._close_phy(obs)
        return alerts

    # ---------------- RF01 ----------------
    def _eval_wifi(self, obs: NormalizedObservation) -> Alert | None:
        ssid = str(obs.data.get("ssid", ""))
        bssid = str(obs.data.get("bssid", "")).lower()
        if not ssid or not bssid:
            return None
        if self.inventory.is_known(ssid, bssid):
            return None
        if not self.inventory.known_bssids.get(ssid):
            return None  # unknown SSID entirely -> not RF01 (new network)
        key = (obs.zone_id, ssid, bssid)
        tr = self._rf.get(key)
        if tr is None:
            tr = _RfTrack(ssid=ssid, bssid=bssid, zone_id=obs.zone_id)
            self._rf[key] = tr
        tr.scan_count += 1
        tr.obs_ids.append(obs.event_id)
        tr.sources.add(obs.source.value)
        if tr.scan_count < RF01_MIN_SCANS:
            return None
        return self._maybe_fire(
            "RF01", "medium", obs.zone_id,
            obs_ids=tr.obs_ids[-RF01_MIN_SCANS:],
            summary=(f"known SSID '{ssid}' seen with unexpected BSSID "
                     f"{bssid} in {tr.scan_count} scans (zone {obs.zone_id})"),
            quality={
                "scans_with_unknown_bssid": tr.scan_count,
                "sources": sorted(tr.sources),
                "ssid_known": True,
                "note": "suspicion only — could be authorized AP change, "
                        "rogue AP, or capture artifact",
            },
        )

    # ---------------- PHY01 ----------------
    def _eval_cabinet(self, obs: NormalizedObservation) -> Alert | None:
        authorized = bool(obs.data.get("authorized", False))
        if authorized:
            # approved maintenance: record but do NOT alert (acceptance:
            # approved maintenance avoids false breach claim)
            self._phy.append(_PhyTrack(
                zone_id=obs.zone_id, obs_ids=[obs.event_id],
                epoch=obs.observed_epoch, authorized=True))
            return None
        tr = _PhyTrack(zone_id=obs.zone_id, obs_ids=[obs.event_id],
                       epoch=obs.observed_epoch, authorized=False)
        self._phy.append(tr)
        return self._maybe_fire(
            "PHY01", "high", obs.zone_id,
            obs_ids=[obs.event_id],
            summary=(f"cabinet contact opened outside maintenance window "
                     f"(zone {obs.zone_id})"),
            quality={
                "authorized": False,
                "maintenance_window": bool(obs.data.get("maintenance_window")),
                "note": "physical anomaly candidate — could be authorized "
                        "work outside recorded window, fault, or tamper",
            },
        )

    def _close_phy(self, obs: NormalizedObservation) -> None:
        # mark most recent open track in zone as closed (no alert change)
        for tr in reversed(self._phy):
            if tr.zone_id == obs.zone_id and not tr.authorized:
                tr.obs_ids.append(obs.event_id)
                return

    # ---------------- CORR01 ----------------
    def _eval_corr(self, phy_alert: Alert) -> list[Alert]:
        """RF01 candidate + PHY01 within corr_window_s, same zone -> CORR01."""
        out = []
        for a in self.alerts:
            if a.rule_id != "RF01" or a.zone_id != phy_alert.zone_id:
                continue
            if a.state != "candidate":
                continue
            dt = abs(phy_alert.fired_at_epoch - a.fired_at_epoch)
            if dt <= self.corr_window_s:
                corr = self._maybe_fire(
                    "CORR01", "high", phy_alert.zone_id,
                    obs_ids=a.observation_ids + phy_alert.observation_ids,
                    summary=(f"RF anomaly ({a.summary}) correlated with "
                             f"physical cabinet event {dt:.0f}s apart in "
                             f"{phy_alert.zone_id} — incident candidate"),
                    quality={
                        "rf01_alert": a.fired_at_epoch,
                        "phy01_alert": phy_alert.fired_at_epoch,
                        "delta_s": round(dt, 1),
                        "window_s": self.corr_window_s,
                        "note": "correlation is circumstantial — investigate, "
                                "do not assert breach",
                    },
                )
                if corr:
                    out.append(corr)
                    self.incidents.append(IncidentCandidate(
                        title=f"Suspected physical+RF anomaly in {phy_alert.zone_id}",
                        zone_id=phy_alert.zone_id,
                        alert_ids=[a.rule_id, phy_alert.rule_id, "CORR01"],
                        evidence=a.observation_ids + phy_alert.observation_ids,
                        confidence="medium — two independent sensor classes agree",
                        alternatives=[
                            "authorized maintenance with unrecorded window",
                            "coincidental unrelated events",
                            "capture/labeling error",
                        ],
                        unknowns=[
                            "whether RF01 BSSID is attacker-controlled",
                            "who opened cabinet and why",
                            "whether data left the zone",
                        ],
                    ))
                break  # one CORR01 per PHY01
        return out

    # ---------------- helpers ----------------
    def _maybe_fire(self, rule: str, severity: str, zone: str,
                    obs_ids: list[str], summary: str,
                    quality: dict) -> Alert | None:
        key = f"{rule}|{zone}|{summary[:48]}"
        now = time.time()
        last = self._fired.get(key, 0)
        if now - last < ALERT_COOLDOWN_S:
            return None
        self._fired[key] = now
        alert = Alert(rule_id=rule, severity=severity, state="candidate",
                      zone_id=zone, observation_ids=obs_ids,
                      summary=summary, evidence_quality=quality)
        self.alerts.append(alert)
        return alert
