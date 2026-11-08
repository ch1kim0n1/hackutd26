"""ServiceBackends — production investigation adapters (#118 follow-up /
BlindSpot task).

Same callable surface as FakeBackends (the ToolRegistry contract), but
every read hits real stored state: persisted backend observations,
incident records, scope-matrix authorized assets, evidence refs, and
rover/mission status observations. Writes are honest proposals/records —
rover inspections are queued requests, containment goes through the real
ContainmentPolicy (propose-only, human approval still required), and
assessments/messages land on the incident record.

The `stores` argument is duck-typed — pass the API AppState (or any
object exposing the same attributes). investigator never imports
sentinel_api, keeping the agent package deployable standalone.

Expected store attributes:
  observations        -> .records: list[ObservationRecord-like dicts]
                         (.all() or iterable of dicts with keys:
                         event_id, kind, device_id, zone_id, incident_id,
                         summary, data, observed_at, provenance)
  incidents           -> IncidentService (.get(iid) -> Incident with
                         .evidence (EvidenceRef), .zone_id, .notes)
  scope_matrix        -> ScopeMatrix (.entries_for_incident(iid))
  policy              -> ContainmentPolicy (.propose(...) -> res)
  mission_requests    -> list[dict] appended by inspection/rescan tools
  agent_assessments   -> list[dict] appended by append_agent_assessment
  agent_messages      -> list[dict] appended by post_incident_system_message
"""
from __future__ import annotations

import time
import uuid
from typing import Any


def _obs_dict(o: Any) -> dict:
    """Normalize an observation record (dataclass or dict) to a dict."""
    if isinstance(o, dict):
        return o
    return {k: getattr(o, k) for k in (
        "event_id", "kind", "device_id", "zone_id", "incident_id",
        "summary", "data", "observed_at", "provenance")
            if hasattr(o, k)}


class ServiceBackends:
    """Tool-callable backends bound to live service state."""

    def __init__(self, stores: Any, incident_id: str):
        self.stores = stores
        self.incident_id = incident_id

    # ---------------- reads ----------------
    def get_recent_observations(self, a: dict[str, Any]):
        """Real persisted observations for this incident's scope:
        incident-linked first, then same-zone device observations."""
        iid = a.get("incident_id") or self.incident_id
        try:
            inc = self.stores.incidents.get(iid)
            zone_id = getattr(inc, "zone_id", "") or ""
        except Exception:
            zone_id = ""
        limit = int(a.get("limit", 10))
        out = []
        for raw in self._all_observations():
            o = _obs_dict(raw)
            oid = o.get("incident_id")
            ozone = o.get("zone_id")
            # In scope: linked to this incident, or unlinked and either
            # zone-less or inside the incident's zone. Unlinked
            # observations from other zones stay out of scope.
            linked = oid == iid
            unlinked_ok = (oid in (None, "")
                           and (not zone_id or not ozone
                                or ozone == zone_id))
            if not (linked or unlinked_ok):
                continue
            out.append({
                "id": o.get("event_id"),
                "kind": o.get("kind"),
                "zone_id": o.get("zone_id"),
                "device_id": o.get("device_id"),
                "summary": o.get("summary"),
                "provenance": o.get("provenance"),
                "observed_at": o.get("observed_at"),
            })
        return {"observations": out[-limit:]}

    def get_authorized_assets(self, a: dict[str, Any]):
        """Scope-matrix entries for this incident = authorized assets."""
        iid = a.get("incident_id") or self.incident_id
        try:
            entries = self.stores.scope_matrix.entries_for_incident(iid)
        except Exception:
            entries = []
        return {"assets": [
            {"id": e.asset_id, "dataset": e.dataset,
             "entry_id": e.entry_id, "version": e.version,
             "evidence_refs": list(e.evidence_refs)}
            for e in entries]}

    def get_rf_activity(self, a: dict[str, Any]):
        """Aggregate RF/wireless observation kinds in the requested zone."""
        zone = a.get("zone_id", "")
        window = int(a.get("time_window_s", 3600))
        now = time.time()
        kinds = {"wifi_ap_seen", "wifi_probe", "ble_beacon",
                 "ble_beacon_seen", "rf_frame_meta", "tag_seen"}
        hits = []
        for raw in self._all_observations():
            o = _obs_dict(raw)
            if o.get("kind") not in kinds:
                continue
            if zone and o.get("zone_id") != zone:
                continue
            ts = o.get("observed_at")
            if isinstance(ts, (int, float)) and now - ts > window:
                continue
            hits.append(o)
        by_kind: dict[str, int] = {}
        devices: set[str] = set()
        for o in hits:
            by_kind[o["kind"]] = by_kind.get(o["kind"], 0) + 1
            if o.get("device_id"):
                devices.add(o["device_id"])
        return {"zone_id": zone, "window_s": window,
                "frame_counts": by_kind, "devices": sorted(devices),
                "note": "metadata-only RF view; no payload contents"}

    def get_rover_status(self, a: dict[str, Any]):
        """Latest rover/mission status observation, if any was ingested."""
        device = a.get("device_id", "")
        latest = None
        for raw in self._all_observations():
            o = _obs_dict(raw)
            if o.get("kind") not in ("mission_status", "device_health"):
                continue
            if device and o.get("device_id") not in ("", device):
                continue
            latest = o
        if latest is None:
            return {"state": "unknown", "device_id": device,
                    "detail": "no rover telemetry ingested"}
        return {"state": "reported", "device_id": latest.get("device_id"),
                "observed_at": latest.get("observed_at"),
                "data": latest.get("data") or {},
                "provenance": latest.get("provenance")}

    # ---------------- action requests (never execute) ----------------
    def request_rover_inspection(self, a: dict[str, Any]):
        """Queue an inspection request record. The mission shim/policy
        path owns actual dispatch — this only registers intent."""
        req = {
            "request_id": f"req-{uuid.uuid4().hex[:10]}",
            "type": "inspect_zone",
            "incident_id": a.get("incident_id") or self.incident_id,
            "zone_id": a.get("zone_id", ""),
            "waypoint_id": a.get("waypoint_id", ""),
            "state": "queued",
            "requested_by": "agent",
            "at": time.time(),
        }
        self.stores.mission_requests.append(req)
        return req

    def request_sensor_rescan(self, a: dict[str, Any]):
        req = {
            "request_id": f"req-{uuid.uuid4().hex[:10]}",
            "type": "sensor_rescan",
            "incident_id": a.get("incident_id") or self.incident_id,
            "device_id": a.get("device_id", ""),
            "state": "queued",
            "requested_by": "agent",
            "at": time.time(),
        }
        self.stores.mission_requests.append(req)
        return {"accepted": True, "request_id": req["request_id"],
                "state": "queued"}

    # ---------------- evidence / assessment / proposals ----------------
    def get_evidence_metadata(self, a: dict[str, Any]):
        eid = a.get("evidence_id", "")
        for raw in self._all_observations():
            o = _obs_dict(raw)
            if o.get("event_id") == eid:
                return {"evidence_id": eid, "kind": "observation",
                        "summary": o.get("summary"),
                        "provenance": o.get("provenance"),
                        "observed_at": o.get("observed_at")}
        try:
            inc = self.stores.incidents.get(self.incident_id)
        except Exception:
            inc = None
        for ref in getattr(inc, "evidence", []) or []:
            rid = getattr(ref, "evidence_id", None) or (
                ref.get("evidence_id") if isinstance(ref, dict) else None)
            if rid == eid:
                return {"evidence_id": eid,
                        "kind": getattr(ref, "kind", "artifact"),
                        "note": getattr(ref, "note", "")}
        return {"error": "not_found", "evidence_id": eid}

    def append_agent_assessment(self, a: dict[str, Any]):
        rec = {
            "id": f"asm-{uuid.uuid4().hex[:10]}",
            "incident_id": a.get("incident_id") or self.incident_id,
            "assessment": a.get("assessment", ""),
            "evidence_ids": list(a.get("evidence_ids", [])),
            "unknowns": list(a.get("unknowns", [])),
            "at": time.time(),
        }
        self.stores.agent_assessments.append(rec)
        try:
            self.stores.incidents.add_note(
                rec["incident_id"], "agent",
                f"assessment {rec['id']}: {rec['assessment'][:200]}")
        except Exception:
            pass  # incident may not exist in this store view
        return {"recorded": True, **rec}

    def propose_containment(self, a: dict[str, Any]):
        """Route through the real ContainmentPolicy — proposal only,
        approval still requires a human via /approvals."""
        iid = a.get("incident_id") or self.incident_id
        try:
            res = self.stores.policy.propose(
                incident_id=iid,
                action_type=a.get("action_type", "isolate_device"),
                target_id=a.get("target_id", ""),
                reason=a.get("reason", "agent-proposed containment"),
                proposer_id="agent",
                proposer_role="agent",  # Role.AGENT may propose
                ttl_s=a.get("ttl_s", 900),
                scope=a.get("scope"))
        except Exception as exc:
            return {"error": f"policy_error: {exc}", "recorded": False}
        if not res.ok:
            return {"recorded": False, "denied": True, "reason": res.reason}
        return {"recorded": True, "proposal_id": res.proposal.proposal_id,
                "state": res.proposal.state,
                "detail": "proposal queued for human approval; "
                          "no containment executed"}

    def post_incident_system_message(self, a: dict[str, Any]):
        rec = {"incident_id": a.get("incident_id") or self.incident_id,
               "message": a.get("message", ""), "at": time.time()}
        self.stores.agent_messages.append(rec)
        try:
            self.stores.incidents.add_note(
                rec["incident_id"], "agent", rec["message"][:500])
        except Exception:
            pass
        return {"posted": True, "id": f"msg-{len(self.stores.agent_messages)}"}

    # ---------------- internals ----------------
    def _all_observations(self):
        store = getattr(self.stores, "observations", None)
        if store is None:
            return []
        recs = getattr(store, "records", store)
        return list(recs()) if callable(recs) else list(recs)

    def as_backends(self) -> dict:
        return {k: getattr(self, k) for k in (
            "get_recent_observations", "get_authorized_assets",
            "get_rf_activity", "get_rover_status",
            "request_rover_inspection", "request_sensor_rescan",
            "get_evidence_metadata", "append_agent_assessment",
            "propose_containment", "post_incident_system_message")}
