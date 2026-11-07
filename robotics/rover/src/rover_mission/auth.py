"""Mission authentication — HMAC-SHA256 over the canonical mission JSON.

The shared device secret comes from environment/config, NEVER the repo
(docs/00: no credentials in repo). Canonical form: JSON with sorted keys,
compact separators, excluding the "signature" field itself.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Mapping, Optional

SIGNATURE_FIELD = "signature"


def canonical_mission_bytes(mission: Mapping) -> bytes:
    payload = {k: v for k, v in mission.items() if k != SIGNATURE_FIELD}
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_mission(mission: Mapping, secret: bytes) -> str:
    return hmac.new(secret, canonical_mission_bytes(mission), hashlib.sha256).hexdigest()


def verify_mission_signature(mission: Mapping, secret: bytes) -> bool:
    sig = mission.get(SIGNATURE_FIELD)
    if not isinstance(sig, str) or not sig:
        return False
    expected = sign_mission(mission, secret)
    return hmac.compare_digest(sig.lower(), expected)


def load_device_secret(env_var: str = "ROVER_MISSION_SECRET") -> bytes:
    """Device credential from environment. Refuses empty/missing secrets —
    an unauthenticated rover must not accept missions."""
    secret = os.environ.get(env_var, "")
    if not secret:
        raise RuntimeError(
            f"{env_var} not set — refusing to run rover without device credential"
        )
    return secret.encode("utf-8")
