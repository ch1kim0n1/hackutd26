"""Sim -> signed MQTT publisher (#100 remainder of #125).

Wraps DataCenterSim: each tick() observation is HMAC-signed (same
canonical form as sensors/pucks + gateway verifyDeviceSignature) and
published to sentinel/v1/<device_id>/telemetry via MQTT env contract
(MQTT_HOST/PORT/USERNAME/PASSWORD/CLIENT_ID). Console fallback for tests.

Trust path: MQTT broker ACL -> gateway validate.ts (envelope + optional
signature) -> ingestObservation (gateway_validated). Device identity
comes from the topic, never the payload.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Callable, Optional

from .simulator import DataCenterSim

SIGNED_FIELDS = ("schema_version", "event_id", "device_id", "seq",
                 "observed_at", "kind", "zone_id", "data")


def canonical_json(value) -> str:
    """Sorted-key compact JSON; ASCII-safe for HMAC parity with gateway."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True)


def sign_observation(obs: dict, secret: bytes) -> str:
    """HMAC-SHA256 over the 8 signed fields, matching gateway verify."""
    body = {k: obs[k] for k in SIGNED_FIELDS}
    return hmac.new(secret, canonical_json(body).encode(),
                    hashlib.sha256).hexdigest()


def verify_observation(obs: dict, secret: bytes) -> bool:
    sig = obs.get("signature", "")
    if not sig:
        return False
    return hmac.compare_digest(sig, sign_observation(obs, secret))


class SimPublisher:
    """Drives DataCenterSim ticks -> signed envelopes -> transport."""

    def __init__(
        self,
        sim: Optional[DataCenterSim] = None,
        secrets: Optional[dict[str, bytes]] = None,
        transport: Optional[Callable[[dict, str], None]] = None,
        state_file: Optional[str] = None,
    ):
        """secrets: {device_id: hmac_secret}; transport(obs, topic).
        state_file persists last seq per device so restarts don't emit
        replay-rejected sequences."""
        self.sim = sim or DataCenterSim()
        self.secrets = secrets or {}
        self.transport = transport or self._default_transport()
        self.published = 0
        self._state_file = state_file
        self._last_seq: dict[str, int] = {}
        if state_file and os.path.exists(state_file):
            try:
                self._last_seq = {
                    k: int(v) for k, v in
                    json.load(open(state_file)).items()}
            except Exception:
                self._last_seq = {}
        # reseed sim node seqs above persisted values
        for nid, last in self._last_seq.items():
            node = self.sim.nodes.get(nid)
            if node is not None:
                node.seq = max(node.seq, last)

    @staticmethod
    def _default_transport() -> Callable[[dict, str], None]:
        host = os.environ.get("MQTT_HOST")
        if host:
            topic_t = os.environ.get("MQTT_TOPIC")  # per-call override below
            return _mqtt_transport(host, topic_t)
        return _console_transport()

    def tick(self) -> list[dict]:
        """Advance sim one tick; sign + publish each observation."""
        out = []
        for obs in self.sim.tick():
            secret = self.secrets.get(obs["device_id"])
            if secret:
                obs["signature"] = sign_observation(obs, secret)
            topic = f"sentinel/v1/{obs['device_id']}/telemetry"
            self.transport(obs, topic)
            self.published += 1
            self._last_seq[obs["device_id"]] = obs["seq"]
            out.append(obs)
        if self._state_file and out:
            try:
                tmp = self._state_file + ".tmp"
                with open(tmp, "w") as fh:
                    json.dump(self._last_seq, fh)
                os.replace(tmp, self._state_file)
            except OSError:
                pass
        return out

    def run(self, ticks: int) -> list[dict]:
        emitted = []
        for _ in range(ticks):
            emitted.extend(self.tick())
        return emitted


def _console_transport() -> Callable[[dict, str], None]:
    import sys

    def pub(obs: dict, topic: str) -> None:
        sys.stdout.write(json.dumps({"topic": topic, "obs": obs},
                                    separators=(",", ":")) + "\n")
    return pub


def _mqtt_transport(host: str, topic_override: Optional[str]):
    port = int(os.environ.get("MQTT_PORT", "1883"))
    username = os.environ.get("MQTT_USERNAME")
    password = os.environ.get("MQTT_PASSWORD")
    client_id = os.environ.get("MQTT_CLIENT_ID", "datacenter-sim")
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        raise RuntimeError("paho-mqtt not installed")

    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                             client_id=client_id)
    except AttributeError:
        client = mqtt.Client(client_id=client_id)
    if username:
        client.username_pw_set(username, password or "")
    client.connect(host, port, keepalive=30)
    client.loop_start()

    def pub(obs: dict, topic: str) -> None:
        # per-device ACL topic; ignore topic_override (it would break ACL)
        client.publish(topic, json.dumps(obs, separators=(",", ":")), qos=1)

    return pub
