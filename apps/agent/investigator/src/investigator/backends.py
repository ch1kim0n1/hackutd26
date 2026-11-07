"""In-memory backends for tests/dev — same callables the real
SpacetimeDB/mission/evidence services will bind (docs/04 touchpoints)."""
from __future__ import annotations

from typing import Any


class FakeBackends:
    """Deterministic stand-ins; every method records calls for assertions."""

    def __init__(self):
        self.observations = [
            {"id": "obs-1", "kind": "wifi_ap_seen", "zone_id": "rack-01",
             "data": {"ssid": "SENTINEL-CORP", "bssid": "02:aa:bb:cc:dd:99"}},
            {"id": "obs-2", "kind": "cabinet_contact_open", "zone_id": "rack-01",
             "data": {"authorized": False}},
        ]
        self.assets = {"rack-01": [{"id": "asset-ap-01", "type": "ap"}]}
        self.rf = {"rack-01": {"channels": {"6": {"count": 3}}}}
        self.rover = {"rover-01": {"state": "idle", "pose": {"x": 0, "y": 0}}}
        self.evidence = {"ev-1": {"sha256": "ab" * 32, "source": "rover-cam",
                                 "trust_tier": "sensor"}}
        self.missions = []
        self.rescans = []
        self.assessments = []
        self.proposals = []
        self.messages = []
        self.calls: dict[str, list] = {}

    def _rec(self, name, args):
        self.calls.setdefault(name, []).append(args)

    def get_recent_observations(self, a: dict[str, Any]):
        self._rec("get_recent_observations", a)
        return {"observations": self.observations[: int(a.get("limit", 10))]}

    def get_authorized_assets(self, a: dict[str, Any]):
        self._rec("get_authorized_assets", a)
        return {"assets": self.assets.get(a["zone_id"], [])}

    def get_rf_activity(self, a: dict[str, Any]):
        self._rec("get_rf_activity", a)
        return self.rf.get(a["zone_id"], {"channels": {}})

    def get_rover_status(self, a: dict[str, Any]):
        self._rec("get_rover_status", a)
        return self.rover.get(a["device_id"], {"state": "unknown"})

    def request_rover_inspection(self, a: dict[str, Any]):
        self._rec("request_rover_inspection", a)
        m = {"mission_id": f"m-{len(self.missions)}", "type": "inspect_zone",
             "zone_id": a["zone_id"], "waypoint_id": a["waypoint_id"],
             "state": "queued"}
        self.missions.append(m)
        return m

    def request_sensor_rescan(self, a: dict[str, Any]):
        self._rec("request_sensor_rescan", a)
        self.rescans.append(a["device_id"])
        return {"accepted": True, "device_id": a["device_id"]}

    def get_evidence_metadata(self, a: dict[str, Any]):
        self._rec("get_evidence_metadata", a)
        ev = self.evidence.get(a["evidence_id"])
        return ev if ev else {"error": "not_found"}

    def append_agent_assessment(self, a: dict[str, Any]):
        self._rec("append_agent_assessment", a)
        rec = {"incident_id": a["incident_id"],
               "assessment": a.get("assessment", ""),
               "evidence_ids": a.get("evidence_ids", []),
               "unknowns": a.get("unknowns", [])}
        self.assessments.append(rec)
        return {"recorded": True, "id": f"asm-{len(self.assessments)}",
                **rec}

    def propose_containment(self, a: dict[str, Any]):
        self._rec("propose_containment", a)
        p = {"proposal_id": f"prop-{len(self.proposals)}", "state": "proposed",
             **a}
        self.proposals.append(p)
        return p

    def post_incident_system_message(self, a: dict[str, Any]):
        self._rec("post_incident_system_message", a)
        self.messages.append(a)
        return {"posted": True}

    def as_backends(self) -> dict:
        return {k: getattr(self, k) for k in (
            "get_recent_observations", "get_authorized_assets",
            "get_rf_activity", "get_rover_status",
            "request_rover_inspection", "request_sensor_rescan",
            "get_evidence_metadata", "append_agent_assessment",
            "propose_containment", "post_incident_system_message")}
