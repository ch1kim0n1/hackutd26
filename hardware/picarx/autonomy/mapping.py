"""
Spatial awareness: log-odds occupancy grid, correlative scan matching, coverage
tracking, frontier detection and grid path planning.

World frame: x forward at start, y left, metres. Pose = (x, y, theta).
"""
import heapq
import math

import numpy as np

L_OCC, L_FREE, L_MIN, L_MAX = 0.85, -0.4, -4.0, 4.0


class Grid:
    def __init__(self, size_m=20.0, res=0.05, robot_radius=0.14):
        self.res = res
        self.n = int(size_m / res)
        self.lo = np.zeros((self.n, self.n), np.float32)          # [iy, ix]
        self.origin = -size_m / 2.0                                # world coord of cell 0
        self.robot_radius = robot_radius
        cres = 0.2
        self.cres = cres
        self.cn = int(size_m / cres)
        self.visits = np.zeros((self.cn, self.cn), np.float32)     # coverage, 20 cm cells

    # ---------------- coordinates ----------------
    def to_cell(self, x, y):
        return ((np.asarray(x) - self.origin) / self.res).astype(int), ((np.asarray(y) - self.origin) / self.res).astype(int)

    def to_world(self, ix, iy):
        return self.origin + (ix + 0.5) * self.res, self.origin + (iy + 0.5) * self.res

    def inside(self, ix, iy):
        return (ix >= 0) & (iy >= 0) & (ix < self.n) & (iy < self.n)

    # ---------------- mapping ----------------
    @staticmethod
    def scan_to_world(pose, angles, ranges):
        x, y, th = pose
        return x + ranges * np.cos(angles + th), y + ranges * np.sin(angles + th)

    def update(self, pose, angles, ranges, max_range=8.0, beam_step=2):
        a, r = angles[::beam_step], ranges[::beam_step]
        hit = r < max_range
        r = np.minimum(r, max_range)
        # free space: sample each beam every half cell up to 1 cell short of the hit
        steps = np.arange(0.0, max_range, self.res * 0.5)
        tt = steps[None, :]
        mask = tt < (r[:, None] - self.res)
        ca, sa = np.cos(a + pose[2]), np.sin(a + pose[2])
        fx = (pose[0] + tt * ca[:, None])[mask]
        fy = (pose[1] + tt * sa[:, None])[mask]
        ix, iy = self.to_cell(fx, fy)
        ok = self.inside(ix, iy)
        free = np.unique(iy[ok] * self.n + ix[ok])
        self.lo.flat[free] += L_FREE
        # hits
        hx, hy = self.scan_to_world(pose, a[hit], r[hit])
        ix, iy = self.to_cell(hx, hy)
        ok = self.inside(ix, iy)
        occ = np.unique(iy[ok] * self.n + ix[ok])
        self.lo.flat[occ] += L_OCC
        np.clip(self.lo, L_MIN, L_MAX, out=self.lo)

    def mark_visited(self, x, y):
        cx = int((x - self.origin) / self.cres)
        cy = int((y - self.origin) / self.cres)
        if 0 <= cx < self.cn and 0 <= cy < self.cn:
            self.visits[cy - 1:cy + 2, cx - 1:cx + 2] += 1     # robot footprint ~ 3x3 coarse cells

    # ---------------- localisation ----------------
    def match(self, guess, angles, ranges, xy_win=0.10, xy_step=0.025, th_win=math.radians(6), th_step=math.radians(1.5)):
        """Correlative scan matching: try poses around the guess, keep the one whose
        scan endpoints land on the most occupied cells. Returns (pose, score)."""
        keep = ranges < 6.0
        a, r = angles[keep][::2], ranges[keep][::2]
        if len(a) < 20:
            return guess, 0.0
        occ = np.maximum(self.lo, 0.0)
        best, best_s = guess, -1.0
        offs = np.arange(-xy_win, xy_win + 1e-9, xy_step)
        for dth in np.arange(-th_win, th_win + 1e-9, th_step):
            th = guess[2] + dth
            px = r * np.cos(a + th)
            py = r * np.sin(a + th)
            # all xy offsets at once
            gx = guess[0] + offs[:, None, None] + px[None, None, :]
            gy = guess[1] + offs[None, :, None] + py[None, None, :]
            ix = ((gx - self.origin) / self.res).astype(int)
            iy = ((gy - self.origin) / self.res).astype(int)
            np.clip(ix, 0, self.n - 1, out=ix)
            np.clip(iy, 0, self.n - 1, out=iy)
            s = occ[iy, ix].sum(axis=2)
            k = np.unravel_index(np.argmax(s), s.shape)
            if s[k] > best_s:
                best_s = float(s[k])
                best = (guess[0] + offs[k[0]], guess[1] + offs[k[1]], th)
        return best, best_s / len(a)

    # ---------------- planning ----------------
    def nav_grid(self, coarse=2):
        """Coarse planning grid (res*coarse): 1 = blocked (obstacle inflated), 0 = free, 2 = unknown."""
        n = self.n // coarse
        lo = self.lo[:n * coarse, :n * coarse].reshape(n, coarse, n, coarse)
        occ = (lo > 0.6).any(axis=(1, 3))
        free = (lo < -0.6).all(axis=(1, 3))
        g = np.full((n, n), 2, np.int8)
        g[free] = 0
        # inflate obstacles by the robot radius
        r = int(math.ceil(self.robot_radius / (self.res * coarse)))
        infl = occ.copy()
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if dx * dx + dy * dy <= r * r:
                    infl |= np.roll(np.roll(occ, dy, 0), dx, 1)
        g[infl] = 1
        return g, self.res * coarse

    def dijkstra(self, g, start, allow_unknown=True):
        """Distances (in cells) from start over the coarse grid. Returns (dist, parent)."""
        n = g.shape[0]
        dist = np.full(g.shape, np.inf, np.float32)
        parent = np.full(g.shape, -1, np.int32)
        sx, sy = start
        if not (0 <= sx < n and 0 <= sy < n):
            return dist, parent
        dist[sy, sx] = 0
        pq = [(0.0, sx, sy)]
        nb = [(1, 0, 1), (-1, 0, 1), (0, 1, 1), (0, -1, 1), (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414)]
        while pq:
            d, x, y = heapq.heappop(pq)
            if d > dist[y, x]:
                continue
            for dx, dy, c in nb:
                nx, ny = x + dx, y + dy
                if 0 <= nx < n and 0 <= ny < n:
                    v = g[ny, nx]
                    if v == 1 or (v == 2 and not allow_unknown):
                        continue
                    nd = d + c * (3.0 if v == 2 else 1.0)       # unknown cells cost more
                    if nd < dist[ny, nx]:
                        dist[ny, nx] = nd
                        parent[ny, nx] = y * n + x
                        heapq.heappush(pq, (nd, nx, ny))
        return dist, parent

    @staticmethod
    def path_to(parent, goal, n):
        gx, gy = goal
        idx = gy * n + gx
        path = []
        while idx >= 0:
            y, x = divmod(int(idx), n)
            path.append((x, y))
            idx = parent[y, x]
        return path[::-1]

    def frontiers(self, g, min_cluster=4):
        """Free cells next to unknown cells; returns list of (x, y, size) cluster centres on g."""
        free = g == 0
        unk = g == 2
        near_unk = np.zeros_like(unk)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            near_unk |= np.roll(np.roll(unk, dy, 0), dx, 1)
        f = free & near_unk
        ys, xs = np.nonzero(f)
        # cluster by 4-cell buckets (cheap, good enough for picking goals)
        buckets = {}
        for x, y in zip(xs, ys):
            buckets.setdefault((x // 4, y // 4), []).append((x, y))
        out = []
        for pts in buckets.values():
            if len(pts) >= min_cluster:
                px, py = pts[len(pts) // 2]
                out.append((px, py, len(pts)))
        return out

    # ---------------- output ----------------
    def to_image(self, path=None, pose=None):
        from PIL import Image, ImageDraw
        p = 1.0 / (1.0 + np.exp(-self.lo))
        img = (255 * (1.0 - p)).astype(np.uint8)
        img[np.abs(self.lo) < 0.05] = 128
        im = Image.fromarray(np.flipud(img)).convert("RGB")
        dr = ImageDraw.Draw(im)
        if path:
            pts = [(x, self.n - 1 - y) for x, y in path]
            if len(pts) > 1:
                dr.line(pts, fill=(0, 160, 255), width=2)
        if pose is not None:
            ix, iy = self.to_cell(pose[0], pose[1])
            iy = self.n - 1 - iy
            dr.ellipse([ix - 4, iy - 4, ix + 4, iy + 4], fill=(255, 60, 60))
            dr.line([ix, iy, ix + 10 * math.cos(pose[2]), iy - 10 * math.sin(pose[2])], fill=(255, 60, 60), width=2)
        return im
