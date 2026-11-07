"""ESP32 motor-controller link — firmware line protocol (robotics/firmware).

Sends JSON commands {"v":1,"kind":"command",...} and reads ack + telemetry
lines. Reconnects with backoff; exposes latest telemetry snapshot so the
navigator/service can react to obstacle/estop/fault without blocking.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass
class RoverTelemetry:
    seq: int = 0
    uptime_ms: int = 0
    state: str = "idle"            # idle|driving|estopped|obstacle_hold|fault
    v_left_mmps: int = 0
    v_right_mmps: int = 0
    odom_dist_mm: int = 0
    odom_heading_rad: float = 0.0
    pose_x_mm: float = 0.0
    pose_y_mm: float = 0.0
    dist_front_mm: int = -1
    dist_rear_mm: int = -1
    estop: bool = False
    obstacle: bool = False
    fault: str = "none"
    led: int = 0
    received_at: float = 0.0

    @property
    def is_obstacle(self) -> bool:
        return self.obstacle or self.state == "obstacle_hold"

    @property
    def is_estopped(self) -> bool:
        return self.estop or self.state == "estopped"

    @property
    def has_fault(self) -> bool:
        return self.state == "fault" or self.fault not in ("none", "")


class MotorLink(Protocol):
    """Transport to the ESP32 motor controller."""

    def connect(self) -> bool: ...
    def close(self) -> None: ...
    def send_command(self, intent: str, cmd_id: str, **params) -> Optional[dict]: ...
    def telemetry(self) -> Optional[RoverTelemetry]: ...
    def pump(self) -> None:
        """Read pending serial data / refresh link state. Called every tick."""
        ...


class SimulatedLink:
    """Deterministic in-memory link for tests and sim runs.

    Mimics firmware behavior: commands accepted/rejected, TTL watchdog,
    obstacle hold, estop. Waypoint navigation in tests uses this so no
    ESP32 is required.
    """

    def __init__(self, tick_s: float = 0.1, telemetry_period_s: float = 0.1):
        self.tick_s = tick_s
        self._t = 0.0
        self._tel_period = telemetry_period_s
        self._tel: Optional[RoverTelemetry] = RoverTelemetry(received_at=0.0)
        self._cmd_seq = 0
        self.connected = True
        self.force_obstacle = False
        self.force_estop = False
        self.force_fault = ""
        self.commands: list = []          # audit log of sent commands
        self.scripted_pose = None         # optional (x,y,heading) override
        self._pending_motion = None       # (intent, params, deadline)
        self._odom_mm = 0.0
        self._pose = (0.0, 0.0, 0.0)

    # -- protocol surface --
    def connect(self) -> bool:
        self.connected = True
        return True

    def close(self) -> None:
        self.connected = False

    def send_command(self, intent: str, cmd_id: str, **params) -> Optional[dict]:
        self._cmd_seq += 1
        self.commands.append(
            {"cmd_id": cmd_id, "intent": intent, "params": params, "t": self._t}
        )
        # Firmware-ish validation
        reason = None
        if self.force_estop and intent not in ("estop_clear", "ping", "stop"):
            reason = "estop"
        elif self._tel and self._tel.state == "obstacle_hold" and intent in (
            "forward", "backward", "turn_left", "turn_right"
        ):
            reason = "obstacle"
        elif intent == "forward" and params.get("speed_mmps", 0) > 250:
            reason = "speed_cap"
        elif intent in ("turn_left", "turn_right") and params.get("rate_dps", 0) > 90:
            reason = "rate_cap"

        if reason:
            return {"accepted": False, "reason": reason}
        if intent == "stop":
            self._pending_motion = None
        elif intent in ("forward", "backward", "turn_left", "turn_right"):
            ttl = params.get("ttl_ms", 500)
            self._pending_motion = (intent, params, self._t + ttl / 1000.0)
        # zero_odometry / estop_clear / set_params / ping: accepted no-ops
        return {"accepted": True}

    def telemetry(self) -> Optional[RoverTelemetry]:
        return self._tel

    def pump(self) -> None:
        """Advance simulated firmware one tick."""
        self._t += self.tick_s
        tel = self._tel
        assert tel is not None
        tel.received_at = self._t
        tel.uptime_ms = int(self._t * 1000)
        tel.estop = self.force_estop
        tel.obstacle = self.force_obstacle
        tel.fault = self.force_fault

        # Watchdog
        if self._pending_motion and self._t >= self._pending_motion[2]:
            self._pending_motion = None
            tel.state = "fault"
            tel.fault = "watchdog_timeout"
            tel.v_left_mmps = tel.v_right_mmps = 0
            return

        if self.force_estop:
            tel.state = "estopped"
            tel.v_left_mmps = tel.v_right_mmps = 0
            return
        if self.force_obstacle and self._pending_motion:
            tel.state = "obstacle_hold"
            tel.obstacle = True
            tel.v_left_mmps = tel.v_right_mmps = 0
            return
        if self.force_fault:
            tel.state = "fault"
            tel.v_left_mmps = tel.v_right_mmps = 0
            return
        if tel.state in ("estopped", "fault", "obstacle_hold") and not (
            self.force_estop or self.force_obstacle or self.force_fault
        ):
            tel.state = "idle"
            tel.fault = "none"

        # Integrate motion -> odometry (kinematic sim)
        if self._pending_motion:
            intent, params, _ = self._pending_motion
            dt = self.tick_s
            if intent == "forward":
                v = params.get("speed_mmps", 0) / 1000.0  # m/s
                self._odom_mm += v * dt * 1000
                x, y, h = self._pose
                self._pose = (x + v * dt * 1000 * math.cos(h),
                              y + v * dt * 1000 * math.sin(h), h)
                tel.v_left_mmps = tel.v_right_mmps = params.get("speed_mmps", 0)
                tel.state = "driving"
            elif intent == "backward":
                v = -params.get("speed_mmps", 0) / 1000.0
                self._odom_mm += abs(v) * dt * 1000
                x, y, h = self._pose
                self._pose = (x + v * dt * 1000 * math.cos(h),
                              y + v * dt * 1000 * math.sin(h), h)
                tel.v_left_mmps = tel.v_right_mmps = -params.get("speed_mmps", 0)
                tel.state = "driving"
            elif intent == "turn_left":
                rate = math.radians(params.get("rate_dps", 0))
                x, y, h = self._pose
                self._pose = (x, y, h + rate * dt)
                tel.v_left_mmps = -50
                tel.v_right_mmps = 50
                tel.state = "driving"
            elif intent == "turn_right":
                rate = math.radians(params.get("rate_dps", 0))
                x, y, h = self._pose
                self._pose = (x, y, h - rate * dt)
                tel.v_left_mmps = 50
                tel.v_right_mmps = -50
                tel.state = "driving"
        else:
            if tel.state == "driving":
                tel.state = "idle"
            tel.v_left_mmps = tel.v_right_mmps = 0

        # Telemetry odometry fields
        x, y, h = self._pose
        if self.scripted_pose is not None:
            x, y, h = self.scripted_pose
        tel.odom_dist_mm = int(self._odom_mm)
        tel.odom_heading_rad = h
        tel.pose_x_mm = x
        tel.pose_y_mm = y
        # ToF: report clear distance unless obstacle forced
        tel.dist_front_mm = 100 if self.force_obstacle else 400
        tel.dist_rear_mm = 400


class Esp32SerialLink:
    """Real link over USB-serial to the ESP32 (pyserial, optional dep)."""

    def __init__(self, port: str, baud: int = 115200, secret: bytes = b""):
        self.port = port
        self.baud = baud
        self._secret = secret
        self._serial = None
        self._tel: Optional[RoverTelemetry] = None
        self._rxbuf = ""
        self._cmd_seq = 0
        self._reconnect_backoff_s = 1.0

    def connect(self) -> bool:
        try:
            import serial  # pyserial — optional dependency
        except ImportError:
            raise RuntimeError("pyserial not installed: pip install pyserial")
        try:
            self._serial = serial.Serial(self.port, self.baud, timeout=0.05)
            self._reconnect_backoff_s = 1.0
            return True
        except Exception:
            self._serial = None
            return False

    def close(self) -> None:
        if self._serial:
            self._serial.close()
            self._serial = None

    def send_command(self, intent: str, cmd_id: str, **params) -> Optional[dict]:
        if not self._serial:
            return None
        self._cmd_seq += 1
        msg = {"v": 1, "kind": "command", "cmd_id": cmd_id, "intent": intent}
        msg.update(params)
        line = json.dumps(msg, separators=(",", ":")) + "\n"
        try:
            self._serial.write(line.encode())
        except Exception:
            return None
        # Ack arrives asynchronously; pump() picks it up. Return None = sent.
        return {"accepted": True, "sent": True}

    def pump(self) -> None:
        if not self._serial:
            return
        try:
            data = self._serial.read(512)
        except Exception:
            self.close()
            return
        if not data:
            return
        self._rxbuf += data.decode("utf-8", errors="replace")
        while "\n" in self._rxbuf:
            line, self._rxbuf = self._rxbuf.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("kind") == "telemetry":
                self._tel = RoverTelemetry(
                    seq=obj.get("seq", 0),
                    uptime_ms=obj.get("uptime_ms", 0),
                    state=obj.get("state", "idle"),
                    v_left_mmps=obj.get("v_left_mmps", 0),
                    v_right_mmps=obj.get("v_right_mmps", 0),
                    odom_dist_mm=obj.get("odom_dist_mm", 0),
                    odom_heading_rad=obj.get("odom_heading_rad", 0.0),
                    pose_x_mm=obj.get("pose_x_mm", 0.0),
                    pose_y_mm=obj.get("pose_y_mm", 0.0),
                    dist_front_mm=obj.get("dist_front_mm", -1),
                    dist_rear_mm=obj.get("dist_rear_mm", -1),
                    estop=bool(obj.get("estop", False)),
                    obstacle=bool(obj.get("obstacle", False)),
                    fault=obj.get("fault", "none"),
                    led=obj.get("led", 0),
                    received_at=time.time(),
                )
            # ack lines are consumed by send_and_wait if used; ignored here

    def telemetry(self) -> Optional[RoverTelemetry]:
        return self._tel
