"""Observation transport — pucks emit signed Observations; transport
delivers them. MQTT to the Sentinel Hive broker (per-device ACL topic),
or console for bench/dev. Same env contract as rover telemetry.py.

Canonical envelope published verbatim (obs.to_dict() — already signed);
the gateway validates envelope + optional HMAC signature upstream.
"""
from __future__ import annotations

import json
import os
from typing import Optional, Protocol

from .models import Observation


class Transport(Protocol):
    def publish(self, obs: Observation) -> None: ...


class ConsoleTransport:
    """Bench/dev: JSON lines to stdout."""

    def __init__(self, stream=None):
        self.stream = stream

    def publish(self, obs: Observation) -> None:
        line = json.dumps(obs.to_dict(), separators=(",", ":"))
        if self.stream is not None:
            self.stream.write(line + "\n")
            self.stream.flush()
        else:
            print(line, flush=True)


class MqttTransport:
    """MQTT uplink (paho-mqtt, lazy import).

    Broker ACLs (deploy/mosquitto/aclfile): device writes ONLY
    sentinel/v1/<device_id>/telemetry — MQTT_TOPIC default is computed
    from MQTT_CLIENT_ID when unset so an ACL mismatch can't publish.
    """

    def __init__(self, host: str, port: int, topic: str, client_id: str):
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            raise RuntimeError("paho-mqtt not installed")
        try:
            self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                       client_id=client_id)
        except AttributeError:  # paho-mqtt 1.x fallback
            self._client = mqtt.Client(client_id=client_id)
        username = os.environ.get("MQTT_USERNAME")
        password = os.environ.get("MQTT_PASSWORD")
        if username:
            self._client.username_pw_set(username, password or "")
        self._topic = topic
        self._client.connect(host, port, keepalive=30)
        self._client.loop_start()

    def publish(self, obs: Observation) -> None:
        self._client.publish(
            self._topic, json.dumps(obs.to_dict()), qos=1)


def transport_from_env(device_id: str, default_topic: Optional[str] = None) -> Transport:
    """MQTT when MQTT_HOST set (username/password via env), else console."""
    if os.environ.get("MQTT_HOST"):
        topic = os.environ.get(
            "MQTT_TOPIC",
            default_topic or f"sentinel/v1/{device_id}/telemetry",
        )
        return MqttTransport(
            os.environ["MQTT_HOST"],
            int(os.environ.get("MQTT_PORT", "1883")),
            topic,
            os.environ.get("MQTT_CLIENT_ID", device_id),
        )
    return ConsoleTransport()
