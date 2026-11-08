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

import json
import time
import uuid
from pathlib import Path
from typing import Any


def _obs_dict(o: Any) -> dict:
    """Normalize an observation record (dataclass or dict) to a dict."""
    if isinstance(o, dict):
        return o
    return {k: getattr(o, k) for k in (
        "event_id", "kind", "device_id", "zone_id", "incident_id",
        "summary", "data", "observed_at", "provenance")
            if hasattr(o, k)}


_MAX_DATA_CHARS = 1500


def _bounded_data(data: Any) -> Any:
    """Structured observation payload, size-bounded for the model
    context. Dicts/lists pass through (truncated on serialize); scalars
    and oversized payloads degrade to a bounded repr — Nemotron sees the
    real telemetry fields, never an opaque summary-only string."""
    if data is None:
        return None
    if isinstance(data, (dict, list)):
        try:
            s = json.dumps(data, separators=(",", ":"), default=str)
        except (TypeError, ValueError):
            return {"_unserializable": True}
        if len(s) <= _MAX_DATA_CHARS:
            return data
        return {"_truncated": True, "bytes": len(s),
                "preview": s[:_MAX_DATA_CHARS]}
    s = str(data)
    return s[:_MAX_DATA_CHARS]


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
                "data": _bounded_data(o.get("data")),
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
        rover = getattr(self.stores, "rover_device_id", "") or "rover-01"
        req = {
            "request_id": f"req-{uuid.uuid4().hex[:10]}",
            "type": "inspect_zone",
            "incident_id": a.get("incident_id") or self.incident_id,
            "device_id": rover,
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
        artifact = self._inspection_artifact(eid)
        if artifact is not None:
            return artifact
        return {"error": "not_found", "evidence_id": eid}

    def _inspection_artifact(self, evidence_id: str):
        """Resolve a rover inspection artifact_id to its stored report.

        The rover writes ``<evidence_dir>/<zone>/<artifact>.json`` +
        ``.meta.json`` sidecars (sha256/bytes/storage_ref). We verify the
        digest before serving content — evidence integrity is part of
        the contract (ADR-008). Returns a bounded summary + the check
        results Nemotron needs for reassessment; the full report stays
        on disk, referenced by storage_ref."""
        root = getattr(self.stores, "rover_evidence_dir", "") or ""
        if not root or not evidence_id:
            return None
        base = Path(root)
        if not base.is_dir():
            return None
        safe = "".join(c if c.isalnum() or c in "-_." else "_"
                       for c in evidence_id)[:96]
        hits = list(base.glob(f"*/{safe}.json")) + \
            list(base.glob(f"{safe}.json"))
        if not hits:
            return None
        report_path = hits[0]
        try:
            body = report_path.read_bytes()
            import hashlib
            digest = hashlib.sha256(body).hexdigest()
            meta = {}
            meta_path = report_path.with_name(
                report_path.name[:-5] + ".meta.json")
            if meta_path.exists():
                meta = json.loads(meta_path.read_text())
            expected = meta.get("sha256")
            if expected and expected != digest:
                return {"evidence_id": evidence_id,
                        "kind": "inspection_report",
                        "error": "sha256_mismatch"}
            report = json.loads(body)
        except (OSError, ValueError):
            return None
        checks = report.get("checks") or []
        return {
            "evidence_id": evidence_id,
            "kind": "inspection_report",
            "report_id": report.get("report_id"),
            "mission_id": report.get("mission_id"),
            "incident_id": report.get("incident_id"),
            "device_id": report.get("device_id"),
            "target_device_id": report.get("target_device_id"),
            "zone_id": report.get("zone_id"),
            "waypoint_id": report.get("waypoint_id"),
            "status": report.get("status"),
            "status_detail": report.get("status_detail"),
            "adapter": report.get("adapter"),
            "provenance": report.get("provenance"),
            "synthetic": report.get("synthetic"),
            "started_at": report.get("started_at"),
            "completed_at": report.get("completed_at"),
            "checks": [{"name": c.get("name") or c.get("type"),
                        "ok": c.get("ok"),
                        "detail": str(c.get("detail") or "")[:200]}
                       for c in checks[:16]],
            "observations": (report.get("observations") or [])[:16],
            "storage_ref": str(report_path),
            "sha256": digest,
        }

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
