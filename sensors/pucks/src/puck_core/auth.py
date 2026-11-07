"""HMAC-SHA256 event signing. Secret arrives via env/keystore, never repo."""
from __future__ import annotations

import hashlib
import hmac
import os

from .models import Observation

ENV_SECRET = "PUCK_DEVICE_SECRET"


def sign(secret: bytes, obs: Observation) -> str:
    return hmac.new(secret, obs.canonical(), hashlib.sha256).hexdigest()


def verify(secret: bytes, obs: Observation) -> bool:
    if not obs.signature:
        return False
    expected = sign(secret, obs)
    return hmac.compare_digest(expected, obs.signature)


def secret_from_env(env: dict[str, str] | None = None) -> bytes:
    env = os.environ if env is None else env
    s = env.get(ENV_SECRET, "")
    if not s:
        raise RuntimeError(f"{ENV_SECRET} not set")
    return s.encode()
