"""Mission/state telemetry publishers.

Every event carries mission_id, device_id, UTC timestamp, zone, pose
confidence and reason (docs/03). Transport is pluggable: HTTP to the
device gateway (production), MQTT (optional), or console for sim/tests.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Optional, Protocol


class Publisher(Protocol):
    def publish(self, event: dict) -> None: ...


class ConsolePublisher:
    def __init__(self, stream=None):
        self.stream = stream

    def publish(self, event: dict) -> None:
        line = json.dumps(event, separators=(",", ":"))
        if self.stream is not None:
            self.stream.write(line + "\n")
            self.stream.flush()
        else:
            print(line, flush=True)


class HttpPublisher:
    """POST events to the device gateway ingest endpoint."""

    def __init__(self, url: str, token: str = "", timeout_s: float = 3.0):
        self.url = url
        self.token = token
        self.timeout_s = timeout_s

    def publish(self, event: dict) -> None:
        body = json.dumps(event).encode()
        req = urllib.request.Request(
            self.url, data=body, method="POST",
            headers={"Content-Type": "application/json",
                     **({"Authorization": f"Bearer {self.token}"} if self.token else {})},
        )
        try:
            urllib.request.urlopen(req, timeout=self.timeout_s).read()
        except Exception:
            # Telemetry loss must not crash the mission loop; gateway dedups
            # by event seq downstream. Log and continue.
            print(f"[telemetry] publish failed: {self.url}", flush=True)


class MqttPublisher:
    """Optional MQTT transport (paho-mqtt). Lazy import.

    Auth via MQTT_USERNAME/MQTT_PASSWORD env (required by the Sentinel Hive
    Mosquitto ACL). Topic must be the per-device ACL topic, e.g.
    sentinel/v1/rover-01/telemetry.
    """

    def __init__(self, host: str, port: int, topic: str, client_id: str):
        try:
            import paho.mqtt.client as mqtt  # noqa: F401
        except ImportError:
            raise RuntimeError("paho-mqtt not installed")
        import paho.mqtt.client as mqtt

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

    def publish(self, event: dict) -> None:
        self._client.publish(self._topic, json.dumps(event), qos=1)


def publisher_from_env(default_url: Optional[str] = None) -> Publisher:
    """Pick transport from env: ROVER_TELEMETRY_URL (http), MQTT_HOST (mqtt),
    else console."""
    url = os.environ.get("ROVER_TELEMETRY_URL", default_url or "")
    if url:
        return HttpPublisher(url, os.environ.get("ROVER_TELEMETRY_TOKEN", ""))
    if os.environ.get("MQTT_HOST"):
        client_id = os.environ.get("MQTT_CLIENT_ID", "rover-01")
        return MqttPublisher(
            os.environ["MQTT_HOST"],
            int(os.environ.get("MQTT_PORT", "1883")),
            os.environ.get("MQTT_TOPIC", f"sentinel/v1/{client_id}/telemetry"),
            client_id,
        )
    return ConsolePublisher()
