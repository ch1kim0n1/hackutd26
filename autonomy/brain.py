"""
Decision layer: Roomba-style behaviours + map-based "where to go next".

Mission (automatic):
  WALL_FOLLOW  hug the right-hand wall to outline the room (stops on loop closure or timeout)
  EXPLORE      drive to the best reachable frontier (edge of known space) until none are left
  PATROL       if rack waypoints are configured, loop through them and stop at each (checkpoint)
  COVER        otherwise keep visiting the least-visited reachable spot (systematic coverage)
Interrupts:
  ESCAPE       stuck detected -> back up, turn to the most open direction, replan
  BOUNCE       planner can't find a path -> Roomba random bounce for a while
  CHECKPOINT   stop for a scan at a waypoint (or when an AprilTag asks for one)
Always on:
  safety filter (corridor clearance) + VFH-lite local steering around obstacles
"""
import math
import random
import time

import numpy as np

from lidar import sector_min


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


class Brain:
    def __init__(self, cfg, grid, on_checkpoint=None):
        self.c = cfg
        self.grid = grid
        self.on_checkpoint = on_checkpoint or (lambda name, pose: None)
        self.mode = "WALL_FOLLOW"
        self.prev_mode = None
        self.t_mode = 0.0
        self.pose = (0.0, 0.0, 0.0)
        self.wf_start = None
        self.travelled = 0.0
        self.last_pose = None
        self.path = []                 # world points
        self.goal = None
        self.t_plan = -99.0
        self.plan_fails = 0
        self.stuck_ref = None
        self.escape = None
        self.bounce_turn = None
        self.wp_index = 0
        self.checkpoint_until = 0.0
        self.pending_checkpoint = None
        self.side_err_prev = 0.0
        self.wall_found = False
        self.wall_lost_t = None
        self.log = []

    # ------------------------------------------------------------------ utils
    def set_mode(self, m, t, why=""):
        if m != self.mode:
            self.log.append((round(t, 1), self.mode, m, why))
            self.prev_mode, self.mode, self.t_mode = self.mode, m, t
            self.path, self.goal = [], None

    def request_checkpoint(self, name):
        """Call from outside (e.g. AprilTag thread) to stop and scan right here."""
        self.pending_checkpoint = name

    @staticmethod
    def robot_points(scan):
        a, r = scan
        return r * np.cos(a), r * np.sin(a)

    def corridor_clearance(self, px, py, heading, half_w=None):
        """Free distance along `heading` (robot frame) for a corridor as wide as the robot."""
        hw = half_w if half_w is not None else self.c["robot_radius"] + 0.03
        ch, sh = math.cos(heading), math.sin(heading)
        fx = px * ch + py * sh
        fy = -px * sh + py * ch
        m = (fx > 0) & (np.abs(fy) < hw)
        return float(fx[m].min()) if m.any() else 12.0

    def vfh_heading(self, px, py, desired, need):
        """Pick the steering direction closest to `desired` that has at least `need` metres free."""
        best, best_cost = None, 1e9
        for h in np.radians(np.arange(-120, 121, 7.5)):
            clr = self.corridor_clearance(px, py, h)
            cost = abs(wrap(h - desired)) + (0 if clr >= need else 3 + (need - clr))
            if cost < best_cost:
                best, best_cost = h, cost
        return best

    def most_open(self, px, py):
        best, best_c = 0.0, -1
        for h in np.radians(np.arange(-180, 180, 15)):
            c = self.corridor_clearance(px, py, h)
            if c > best_c:
                best, best_c = h, c
        return best, best_c

    # ------------------------------------------------------------------ planning
    def plan(self, t, kind):
        g, cres = self.grid.nav_grid()
        n = g.shape[0]
        sx = int((self.pose[0] - self.grid.origin) / cres)
        sy = int((self.pose[1] - self.grid.origin) / cres)
        dist, parent = self.grid.dijkstra(g, (sx, sy))
        goal = None
        if kind == "frontier":
            best = None
            for fx, fy, size in self.grid.frontiers(g):
                d = dist[fy, fx]
                if np.isfinite(d) and d > 3:
                    score = d - 1.5 * size
                    if best is None or score < best[0]:
                        best = (score, fx, fy)
            goal = best[1:] if best else None
        elif kind == "cover":
            free = (g == 0) & np.isfinite(dist) & (dist > 6)
            if free.any():
                vis = self.grid.visits
                k = self.grid.cres / cres            # coarse->coverage scale
                ys, xs = np.nonzero(free)
                v = vis[np.minimum((ys / k).astype(int), vis.shape[0] - 1), np.minimum((xs / k).astype(int), vis.shape[1] - 1)]
                score = v * 4.0 + dist[ys, xs] * 0.05 + np.random.rand(len(xs)) * 0.5
                i = int(np.argmin(score))
                goal = (xs[i], ys[i])
        elif kind == "waypoint":
            wx, wy = self.c["waypoints"][self.wp_index]["xy"]
            gx = int((wx - self.grid.origin) / cres)
            gy = int((wy - self.grid.origin) / cres)
            if 0 <= gx < n and 0 <= gy < n and np.isfinite(dist[gy, gx]):
                goal = (gx, gy)
        self.t_plan = t
        if goal is None:
            self.path, self.goal = [], None
            return False
        cells = self.grid.path_to(parent, goal, n)[::2] + [goal]
        self.path = [(self.grid.origin + (x + 0.5) * cres, self.grid.origin + (y + 0.5) * cres) for x, y in cells]
        self.goal = self.path[-1]
        return True

    def follow_path(self, px, py):
        """Pure-pursuit on self.path with VFH-lite avoidance. Returns (v, w, reached)."""
        x, y, th = self.pose
        while len(self.path) > 1 and math.hypot(self.path[0][0] - x, self.path[0][1] - y) < self.c["lookahead"]:
            self.path.pop(0)
        if not self.path:
            return 0.0, 0.0, True
        tx, ty = self.path[0]
        if len(self.path) == 1 and math.hypot(tx - x, ty - y) < self.c["goal_tol"]:
            return 0.0, 0.0, True
        desired = wrap(math.atan2(ty - y, tx - x) - th)
        h = self.vfh_heading(px, py, desired, need=0.45)
        err = h
        w = max(-self.c["w_max"], min(self.c["w_max"], 2.2 * err))
        v = self.c["v_max"] * max(0.0, math.cos(err)) ** 2
        if abs(err) > math.radians(60):
            v = 0.0                                      # turn in place first
        return v, w, False

    # ------------------------------------------------------------------ behaviours
    def wall_follow(self, px, py, scan, t):
        """Roomba wall-follow: drive straight until a wall is found, then keep it on the right."""
        a, r = scan
        d0 = self.c["wall_dist"]
        front = self.corridor_clearance(px, py, 0.0)
        side = sector_min(a, r, -105, -75)
        front_right = sector_min(a, r, -60, -30)
        if not self.wall_found:
            if front < d0 + 0.3 or side < d0 + 0.2:
                self.wall_found = True
                self.wf_start = None                 # loop-closure reference = where the wall was found
            else:
                return self.c["v_max"], 0.0          # head straight for a wall
        if front < d0 + 0.15:
            self.wall_lost_t = None
            return 0.0, self.c["w_max"] * 0.8        # inside corner: turn left in place
        if side > 1.0 and front_right > 1.0:
            if self.wall_lost_t is None:
                self.wall_lost_t = t
            if t - self.wall_lost_t > 4.0:           # really lost it: go find another wall
                self.wall_found = False
                self.wall_lost_t = None
            return self.c["v_max"] * 0.6, -1.0       # outside corner: arc right around it
        self.wall_lost_t = None
        meas = min(side, front_right * math.cos(math.radians(45)))
        err = d0 - meas                              # >0 too close -> turn left
        derr = err - self.side_err_prev
        self.side_err_prev = err
        w = max(-self.c["w_max"], min(self.c["w_max"], 3.0 * err + 6.0 * derr))
        return self.c["v_max"] * 0.8, w

    def bounce(self, px, py, t):
        front = self.corridor_clearance(px, py, 0.0)
        if self.bounce_turn is None and front < 0.35:
            h, _ = self.most_open(px, py)
            self.bounce_turn = wrap(self.pose[2] + h + random.uniform(-0.6, 0.6))
        if self.bounce_turn is not None:
            err = wrap(self.bounce_turn - self.pose[2])
            if abs(err) < 0.15:
                self.bounce_turn = None
            return 0.0, math.copysign(self.c["w_max"] * 0.8, err)
        return self.c["v_max"], 0.0

    # ------------------------------------------------------------------ main step
    def step(self, t, scan, pose):
        self.pose = pose
        if self.last_pose is not None:
            self.travelled += math.hypot(pose[0] - self.last_pose[0], pose[1] - self.last_pose[1])
        self.last_pose = pose
        self.grid.mark_visited(pose[0], pose[1])
        px, py = self.robot_points(scan)

        # ---- external checkpoint request (AprilTag etc.)
        if self.pending_checkpoint and self.mode != "CHECKPOINT":
            self._start_checkpoint(t, self.pending_checkpoint)
        # ---- stuck detection
        if self.mode not in ("ESCAPE", "CHECKPOINT"):
            self._check_stuck(t, px, py)

        m = self.mode
        if m == "CHECKPOINT":
            if t >= self.checkpoint_until:
                self.set_mode(self.prev_mode if self.prev_mode != "CHECKPOINT" else "COVER", t, "checkpoint done")
            v, w = 0.0, 0.0
        elif m == "ESCAPE":
            v, w = self._escape(t, px, py)
        elif m == "WALL_FOLLOW":
            v, w = self.wall_follow(px, py, scan, t)
            if self.wall_found and self.wf_start is None:
                self.wf_start = (pose, self.travelled)
            back_home = bool(self.wf_start) and math.hypot(pose[0] - self.wf_start[0][0], pose[1] - self.wf_start[0][1]) < 0.4
            if (back_home and self.travelled - self.wf_start[1] > self.c["loop_min_m"]) or t - self.t_mode > self.c["wall_follow_s"]:
                self.set_mode("EXPLORE", t, "outline done" if back_home else "wall-follow timeout")
        elif m in ("EXPLORE", "COVER", "PATROL"):
            v, w = self._planned(t, px, py)
        elif m == "BOUNCE":
            v, w = self.bounce(px, py, t)
            if t - self.t_mode > self.c["bounce_s"]:
                self.set_mode(self.prev_mode if self.prev_mode in ("EXPLORE", "COVER", "PATROL") else "EXPLORE", t, "bounce done")
        else:
            v, w = 0.0, 0.0
        return self.safety(px, py, v, w)

    def _planned(self, t, px, py):
        kind = {"EXPLORE": "frontier", "COVER": "cover", "PATROL": "waypoint"}[self.mode]
        blocked_ahead = self.path and self.corridor_clearance(px, py, 0.0) < 0.25
        if not self.path or t - self.t_plan > self.c["replan_s"] or blocked_ahead:
            if not self.plan(t, kind):
                self.plan_fails += 1
                if self.mode == "EXPLORE" and self.plan_fails >= 3:
                    self.plan_fails = 0
                    nxt = "PATROL" if self.c.get("waypoints") else "COVER"
                    self.set_mode(nxt, t, "map explored")
                elif self.plan_fails >= 5:
                    self.plan_fails = 0
                    self.set_mode("BOUNCE", t, "no path")
                return 0.0, 0.4
            self.plan_fails = 0
        v, w, reached = self.follow_path(px, py)
        if reached:
            if self.mode == "PATROL":
                wp = self.c["waypoints"][self.wp_index]
                self.wp_index = (self.wp_index + 1) % len(self.c["waypoints"])
                self._start_checkpoint(t, wp["name"])
            self.path = []
        return v, w

    def _start_checkpoint(self, t, name):
        self.pending_checkpoint = None
        self.set_mode("CHECKPOINT", t, f"scan at {name}")
        self.checkpoint_until = t + self.c["checkpoint_s"]
        self.on_checkpoint(name, self.pose)

    def _check_stuck(self, t, px, py):
        if self.stuck_ref is None or t - self.stuck_ref[1] > self.c["stuck_window_s"]:
            if self.stuck_ref is not None:
                (x0, y0, th0), _ = self.stuck_ref
                moved = math.hypot(self.pose[0] - x0, self.pose[1] - y0)
                turned = abs(wrap(self.pose[2] - th0))
                trying = self.mode not in ("CHECKPOINT",)
                if trying and moved < 0.05 and turned < 0.15:
                    self._start_escape(t, px, py)
            self.stuck_ref = (self.pose, t)

    def _start_escape(self, t, px, py):
        h, _ = self.most_open(px, py)
        self.escape = {"t0": t, "target": wrap(self.pose[2] + h), "resume": self.mode}
        self.set_mode("ESCAPE", t, "stuck")

    def _escape(self, t, px, py):
        e = self.escape
        dt = t - e["t0"]
        rear = self.corridor_clearance(px, py, math.pi)
        if dt < 0.8 and rear > 0.25:
            return -0.12, 0.0                                  # back up
        err = wrap(e["target"] - self.pose[2])
        if abs(err) > 0.15 and dt < 4.0:
            return 0.0, math.copysign(self.c["w_max"] * 0.8, err)
        resume = e["resume"] if e["resume"] not in ("ESCAPE", "CHECKPOINT") else "EXPLORE"
        self.stuck_ref = None
        self.set_mode(resume, t, "escaped")
        return 0.0, 0.0

    # ------------------------------------------------------------------ safety
    def safety(self, px, py, v, w):
        stop = self.c["stop_dist"]
        if v > 0:
            clr = self.corridor_clearance(px, py, 0.0)
            if clr < stop:
                v = 0.0
            else:
                v = min(v, self.c["v_max"] * min(1.0, (clr - stop) / 0.5) + 0.03)
        elif v < 0:
            if self.corridor_clearance(px, py, math.pi) < stop * 0.8:
                v = 0.0
        return v, max(-self.c["w_max"], min(self.c["w_max"], w))
