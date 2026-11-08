"""Hardware adapter contract tests (issue #117).

Every physical boundary must have: a typed protocol, a fake/simulated
implementation, and a contract test proving the fake satisfies the
protocol. Real-hardware implementations (Esp32SerialLink, Cv2Camera,
MqttTransport) are constructed/shape-checked only — no hardware claims.
"""
import pytest

from rover_mission.camera import Cv2Camera, Frame, SyntheticCamera
from rover_mission.localization import NoopDetector, PoseEstimator
from rover_mission.motor_link import (
    Esp32SerialLink, RoverTelemetry, SimulatedLink,
)
from rover_mission.telemetry import (
    ConsolePublisher, MqttPublisher, HttpPublisher, publisher_from_env,
)


def _conforms(link, protocol_attrs):
    return all(hasattr(link, a) for a in protocol_attrs)


MOTORLINK_ATTRS = ["connect", "close", "send_command", "telemetry", "pump"]


# ---------------- rover pose/commands boundary ----------------

def test_simulated_link_satisfies_motorlink_protocol():
    link = SimulatedLink()
    assert _conforms(link, MOTORLINK_ATTRS)
    # Fake behaves like the protocol: connect, command, telemetry, pump.
    assert link.connect() is True
    resp = link.send_command("drive", "cmd-1", v_mmps=100, w_radps=0.0)
    assert resp is None or isinstance(resp, dict)
    link.pump()
    tel = link.telemetry()
    assert tel is None or isinstance(tel, RoverTelemetry)
    link.close()


def test_esp32_serial_link_has_protocol_surface():
    """Hardware link: shape only — no serial device touched."""
    link = Esp32SerialLink(port="/dev/null", baud=115200)
    assert _conforms(link, MOTORLINK_ATTRS)
    link.close()


def test_motorlink_telemetry_safety_flags():
    assert RoverTelemetry(state="estopped", estop=True).is_estopped
    assert RoverTelemetry(state="obstacle_hold", obstacle=True).is_obstacle
    assert RoverTelemetry(state="fault", fault="encoder_timeout").has_fault
    assert not RoverTelemetry(state="idle").has_fault


# ---------------- localization / AprilTag boundary ----------------

def test_noop_detector_satisfies_tagdetector():
    det = NoopDetector()
    assert hasattr(det, "detect")
    assert det.detect(None) == []


def test_pose_estimator_odometry_only():
    # No tags -> estimator still produces a pose (odometry-only fallback).
    est = PoseEstimator({})
    assert est.pose is not None


# ---------------- camera boundary ----------------

def test_synthetic_camera_satisfies_camera_protocol():
    cam = SyntheticCamera(width=8, height=8)
    assert hasattr(cam, "capture")
    frame = cam.capture()
    assert isinstance(frame, Frame)
    assert frame.data.startswith(b"SYNTHETIC-FRAME")
    assert frame.width == 8 and frame.height == 8
    # Second capture differs (monotonic counter) — never a real photo.
    assert cam.capture().data != frame.data


def test_cv2_camera_is_lazy_and_honest():
    """Real camera requires cv2 + device; failure must be explicit."""
    try:
        cam = Cv2Camera(device=9999)
    except Exception as exc:
        assert "opencv" in str(exc).lower() or "camera" in str(exc).lower()
    else:  # pragma: no cover - only on machines with a camera at idx 9999
        pytest.skip("unexpected camera present")


# ---------------- telemetry publisher boundary ----------------

def test_publisher_from_env_defaults_console(monkeypatch):
    for var in ("ROVER_TELEMETRY_URL", "MQTT_HOST"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("ROVER_TELEMETRY_URL", raising=False)
    pub = publisher_from_env()
    assert isinstance(pub, ConsolePublisher)


def test_publisher_from_env_selects_http(monkeypatch):
    monkeypatch.setenv("ROVER_TELEMETRY_URL", "http://127.0.0.1:9/ingest")
    pub = publisher_from_env()
    assert isinstance(pub, HttpPublisher)


def test_publisher_from_env_selects_mqtt(monkeypatch):
    monkeypatch.delenv("ROVER_TELEMETRY_URL", raising=False)
    monkeypatch.setenv("MQTT_HOST", "127.0.0.1")
    try:
        pub = publisher_from_env()
    except RuntimeError as exc:
        pytest.skip(f"paho-mqtt unavailable: {exc}")
    assert isinstance(pub, MqttPublisher)
    pub._client.disconnect()


def test_console_publisher_emits_json_line():
    import io, json
    buf = io.StringIO()
    pub = ConsolePublisher(stream=buf)
    pub.publish({"event": "test", "n": 1})
    line = json.loads(buf.getvalue().strip())
    assert line["event"] == "test"
