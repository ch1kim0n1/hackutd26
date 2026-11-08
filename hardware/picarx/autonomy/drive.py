"""
Differential drive output + dead-reckoning.

DiffDrive.set(v, w): v = forward m/s, w = turn rad/s (CCW positive).
Wheel PWM = (v -/+ w*track/2) / max_wheel_speed, clamped to [-1, 1].
Without wheel encoders the odometry is the commanded motion scaled by a
calibration factor; scan matching corrects the drift.
"""
import math
import time


class DiffDrive:
    def __init__(self, cfg):
        self.track = cfg["track_m"]
        self.vmax = cfg["max_wheel_speed"]
        self.cal_v = cfg.get("odom_scale_v", 1.0)
        self.cal_w = cfg.get("odom_scale_w", 1.0)
        self.deadband = cfg.get("pwm_deadband", 0.18)
        self.v = self.w = 0.0
        from gpiozero import Motor, DigitalOutputDevice
        p = cfg["pins"]
        self.left = Motor(forward=p["ain1"], backward=p["ain2"], enable=p["pwma"], pwm=True)
        self.right = Motor(forward=p["bin1"], backward=p["bin2"], enable=p["pwmb"], pwm=True)
        self.stby = DigitalOutputDevice(p["stby"], initial_value=True)
        self.flip_l = cfg.get("invert_left", False)
        self.flip_r = cfg.get("invert_right", False)

    def _pwm(self, motor, speed, flip):
        s = max(-1.0, min(1.0, speed / self.vmax))
        if flip:
            s = -s
        if abs(s) < 0.02:
            motor.stop()
            return
        s = math.copysign(self.deadband + (1 - self.deadband) * abs(s), s)   # overcome motor stiction
        motor.forward(s) if s > 0 else motor.backward(-s)

    def set(self, v, w):
        self.v, self.w = v, w
        self._pwm(self.left, v - w * self.track / 2, self.flip_l)
        self._pwm(self.right, v + w * self.track / 2, self.flip_r)

    def stop(self):
        self.set(0.0, 0.0)

    def odom_delta(self, dt):
        """Estimated (forward m, turn rad) moved in dt from the last command."""
        return self.v * self.cal_v * dt, self.w * self.cal_w * dt
