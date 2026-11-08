"""
Tiny 2D simulator so the autonomy stack can be tested without the car:
a room with server racks, a ray-cast 2D LiDAR with noise, and a differential-drive
robot with wheel slip and odometry bias (so scan matching has real work to do).
"""
import math
import random

import numpy as np


def rect_segments(x0, y0, x1, y1):
    return [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))]


class SimWorld:
    def __init__(self, layout="datacenter", seed=1):
        random.seed(seed)
        np.random.seed(seed)
        self.rects = []
        if layout == "datacenter":
            # 7 m x 5 m room centred so the robot starts at (0,0) facing +x
            room = (-1.0, -2.0, 6.0, 3.0)
            self.walls = rect_segments(*room)
            # two rows of racks (0.6 x 1.2 m) with a 1.2 m aisle between, plus a box
            for i in range(4):
                self.rects.append((0.6 + i * 1.3, 1.2, 1.2 + i * 1.3, 2.4))     # top row
                self.rects.append((0.6 + i * 1.3, -1.6, 1.2 + i * 1.3, -0.6))   # bottom row
            self.rects.append((5.2, -0.3, 5.6, 0.3))                             # cart in the aisle end
        else:
            self.walls = rect_segments(-1.0, -1.0, 4.0, 3.0)
        segs = list(self.walls)
        for r in self.rects:
            segs += rect_segments(*r)
        s = np.array(segs, dtype=float)         # (S, 2, 2)
        self.p = s[:, 0, :]
        self.d = s[:, 1, :] - s[:, 0, :]
        self.pose = [0.0, 0.0, 0.0]             # true pose
        self.radius = 0.13
        self.collisions = 0
        self.slip = 0.04
        self.bias_v, self.bias_w = 1.06, 0.95   # odometry is wrong by this much

    # -------- lidar --------
    def scan(self, n=360, noise=0.01, max_r=12.0):
        x, y, th = self.pose
        ang = np.linspace(-math.pi, math.pi, n, endpoint=False)
        dirs = np.stack([np.cos(ang + th), np.sin(ang + th)], axis=1)    # (B,2)
        # ray o + t*dir vs segment p + u*d  ->  solve 2x2 per pair
        o = np.array([x, y])
        dx, dy = dirs[:, 0][:, None], dirs[:, 1][:, None]
        sx, sy = self.d[:, 0][None, :], self.d[:, 1][None, :]
        den = dx * sy - dy * sx
        qx = (self.p[:, 0] - o[0])[None, :]
        qy = (self.p[:, 1] - o[1])[None, :]
        with np.errstate(divide="ignore", invalid="ignore"):
            t = (qx * sy - qy * sx) / den
            u = (qx * dy - qy * dx) / den
        valid = (np.abs(den) > 1e-9) & (t > 0) & (u >= 0) & (u <= 1)
        t = np.where(valid, t, np.inf)
        r = t.min(axis=1)
        r = np.minimum(r, max_r) + np.random.normal(0, noise, n)
        keep = (np.random.rand(n) > 0.03) & (r < max_r - 0.01)          # 3 % dropouts
        return ang[keep], r[keep]

    # -------- motion --------
    def blocked(self, x, y):
        rr = self.radius
        x0, y0, x1, y1 = -1.0, -2.0, 6.0, 3.0
        if not (x0 + rr < x < x1 - rr and y0 + rr < y < y1 - rr):
            return True
        for (a, b, c, d) in self.rects:
            cx, cy = min(max(x, a), c), min(max(y, b), d)
            if (x - cx) ** 2 + (y - cy) ** 2 < rr * rr:
                return True
        return False

    def step(self, v, w, dt):
        x, y, th = self.pose
        v_t = v * (1 + random.gauss(0, self.slip))
        w_t = w * (1 + random.gauss(0, self.slip))
        nth = th + w_t * dt
        nx = x + v_t * dt * math.cos(th + w_t * dt / 2)
        ny = y + v_t * dt * math.sin(th + w_t * dt / 2)
        if self.blocked(nx, ny):
            self.collisions += 1
            self.pose[2] = nth          # can still rotate in place
            return 0.0, w * self.bias_w * dt
        self.pose = [nx, ny, nth]
        return v * self.bias_v * dt, w * self.bias_w * dt     # what the (biased) odometry reports


class SimDrive:
    """Same interface as drive.DiffDrive, moving the simulated robot."""

    def __init__(self, world):
        self.world = world
        self.v = self.w = 0.0
        self._odom = (0.0, 0.0)

    def set(self, v, w):
        self.v, self.w = v, w

    def stop(self):
        self.set(0.0, 0.0)

    def advance(self, dt):
        self._odom = self.world.step(self.v, self.w, dt)

    def odom_delta(self, dt):
        return self._odom
