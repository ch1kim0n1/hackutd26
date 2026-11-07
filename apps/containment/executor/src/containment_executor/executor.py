"""Lab executor — consumes approved outbox items, applies via lab-only
adapter, then INDEPENDENTLY verifies before claiming success.

State honesty (docs/08 threat 3): STARTED -> API_ACKED are adapter
claims; only VERIFIED reflects the independent probe. A simulated API
200 where the target stays reachable records FAILED, never VERIFIED."""
from __future__ import annotations

from .adapters import LabAdapter, VerifyAdapter
from .models import ExecState
from .outbox import Outbox

VERIFY_ATTEMPTS = 3
VERIFY_DELAY_S = 0.0  # real impl: short settle delay configurable


class Executor:
    def __init__(self, outbox: Outbox, lab: LabAdapter,
                 verify: VerifyAdapter):
        self.outbox = outbox
        self.lab = lab
        self.verify = verify

    def run_once(self) -> list:
        """Process all pending approved actions. Returns records."""
        done = []
        for item in self.outbox.pending():
            done.append(self.execute(item))
        return done

    def execute(self, item) -> object:
        rec = self.outbox.records[item.action_id]
        # guard: only QUEUED records execute
        if rec.state != ExecState.QUEUED:
            return rec
        rec.transition(ExecState.STARTED, adapter="lab")
        try:
            resp = self.lab.apply_isolation(item.target_id, item.action_type)
        except Exception as e:
            rec.api_response = {"error": str(e)}
            rec.transition(ExecState.FAILED, stage="apply", error=str(e))
            self.outbox.complete(item.action_id)
            return rec
        rec.api_response = resp if isinstance(resp, dict) else {"raw": resp}
        if not (isinstance(resp, dict) and resp.get("ok", True)):
            rec.transition(ExecState.FAILED, stage="api",
                           error=resp.get("error", "adapter refused"))
            self.outbox.complete(item.action_id)
            return rec
        rec.transition(ExecState.API_ACKED)
        # ---- independent verification — the ONLY path to VERIFIED ----
        ok = self._verify(item)
        if ok:
            rec.verification = {"method": "independent_probe",
                                "effective": True}
            rec.transition(ExecState.VERIFIED)
        else:
            rec.verification = {"method": "independent_probe",
                                "effective": False,
                                "note": "API ack did not produce verified "
                                        "state — recorded as failure"}
            rec.transition(ExecState.FAILED, stage="verification",
                           error="isolation not independently verified")
        self.outbox.complete(item.action_id)
        return rec

    def _verify(self, item) -> bool:
        """Poll the independent probe; reachability must be gone for
        isolation actions. Never consults api_response."""
        for _ in range(VERIFY_ATTEMPTS):
            if self.verify.isolation_effective(item.target_id,
                                               item.action_type):
                # belt: also confirm endpoint actually unreachable
                if not self.verify.target_reachable(item.target_id):
                    return True
            # settle delay hook for real networks
        return False

    # ---------------- recovery path (used by #35) ----------------
    def revert(self, item, verify: VerifyAdapter | None = None) -> object:
        """Remove isolation + verify restoration. Same honesty rules."""
        rec = self.outbox.records.get(item.action_id)
        if rec is None:
            return None
        try:
            self.lab.remove_isolation(item.target_id, item.action_type)
        except Exception as e:
            rec.transition(ExecState.FAILED, stage="revert", error=str(e))
            return rec
        v = verify or self.verify
        restored = all(v.target_reachable(item.target_id)
                       for _ in range(VERIFY_ATTEMPTS))
        rec.verification["revert"] = {"restored": restored}
        rec.transition(ExecState.VERIFIED if restored else ExecState.FAILED,
                       stage="revert_verify")
        return rec
