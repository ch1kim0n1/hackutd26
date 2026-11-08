#!/usr/bin/env python3
"""
Rover ground autonomy main loop.

  python3 run.py --sim --duration 300 --fast      # simulated data-center room, faster than real time
  sudo python3 run.py                              # real rover: MS200 on serial + TB6612 motors

Loop (10 Hz): odometry predict -> scan match -> map update -> brain decides (v, w) -> safety -> motors.
Writes map.png (and optionally POSTs pose/mode/map to the backend) every few seconds.
"""
import argparse
import json
import math
import os
import time

import yaml

from brain import Brain
from mapping import Grid

HERE = os.path.dirname(os.path.abspath(__file__))


def compose(pose, d, dth):
    x, y, th = pose
    return (x + d * math.cos(th + dth / 2), y + d * math.sin(th + dth / 2), th + dth)


def save_report(grid, pose, traj_est, traj_true, brain, path):
    """Cropped, enlarged map with the driven route (blue = estimated, green = true in sim)."""
    import numpy as np
    from PIL import Image, ImageDraw
    known = (grid.lo > 0.6) | (grid.lo < -0.6)
    ys, xs = np.nonzero(known)
    if len(xs) == 0:
        return
    pad = 10
    x0, x1 = max(xs.min() - pad, 0), min(xs.max() + pad, grid.n - 1)
    y0, y1 = max(ys.min() - pad, 0), min(ys.max() + pad, grid.n - 1)
    p = 1.0 / (1.0 + np.exp(-grid.lo[y0:y1 + 1, x0:x1 + 1]))
    img = (255 * (1.0 - p)).astype(np.uint8)
    img[np.abs(grid.lo[y0:y1 + 1, x0:x1 + 1]) < 0.05] = 150
    S = 6
    im = Image.fromarray(np.flipud(img)).convert("RGB").resize(((x1 - x0 + 1) * S, (y1 - y0 + 1) * S), Image.NEAREST)
    dr = ImageDraw.Draw(im)
    H = (y1 - y0 + 1) * S

    def px(x, y):
        return ((x - grid.origin) / grid.res - x0) * S, H - ((y - grid.origin) / grid.res - y0) * S

    for traj, col in ((traj_true, (40, 190, 90)), (traj_est, (0, 140, 255))):
        if len(traj) > 1:
            dr.line([px(*q) for q in traj], fill=col, width=3)
    for wp in brain.c.get("waypoints") or []:
        cx, cy = px(*wp["xy"])
        dr.rectangle([cx - 7, cy - 7, cx + 7, cy + 7], outline=(255, 150, 0), width=3)
    cx, cy = px(pose[0], pose[1])
    dr.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], fill=(255, 60, 60))
    im.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim", action="store_true", help="run in the built-in simulator")
    ap.add_argument("--duration", type=float, default=0, help="stop after N seconds (0 = forever)")
    ap.add_argument("--fast", action="store_true", help="sim only: run faster than real time")
    ap.add_argument("--config", default=os.path.join(HERE, "config.yaml"))
    ap.add_argument("--out", default=os.path.join(HERE, "out"))
    ap.add_argument("--pose-stream", default="",
                    help="append JSONL pose fixes here for the sim-to-twin "
                         "bridge (rover_mission.sim_bridge); sim only")
    args = ap.parse_args()
    cfg = yaml.safe_load(open(args.config))
    os.makedirs(args.out, exist_ok=True)

    grid = Grid(cfg["map"]["size_m"], cfg["map"]["res_m"], cfg["brain"]["robot_radius"])
    checkpoints = []

    def on_checkpoint(name, pose):
        checkpoints.append((name, round(pose[0], 2), round(pose[1], 2)))
        print(f"[checkpoint] {name} at ({pose[0]:.2f}, {pose[1]:.2f}) -> trigger Wi-Fi scan here")

    brain = Brain(cfg["brain"], grid, on_checkpoint)

    if args.sim:
        from sim import SimDrive, SimWorld
        world = SimWorld()
        drive = SimDrive(world)
        lidar = None
    else:
        from drive import DiffDrive
        from lidar import PipeLidar, SerialLidar
        drive = DiffDrive(cfg["drive"])
        L = cfg["lidar"]
        if L["mode"] == "serial":
            lidar = SerialLidar(L["port"], L["baud"], L["mount_offset_deg"], L["clockwise"])
        else:
            lidar = PipeLidar(L["pipe_cmd"], L["mount_offset_deg"], L["clockwise"])

    dt = 1.0 / cfg["loop_hz"]
    pose = (0.0, 0.0, 0.0)
    t, last_stamp, n_scans, last_save = 0.0, 0.0, 0, -99.0
    match_scores = []
    traj_est, traj_true = [], []
    t_wall0 = time.time()
    poster = None
    if cfg.get("backend_url") and not args.sim:
        import requests
        poster = requests.Session()

    try:
        while not args.duration or t < args.duration:
            loop_start = time.time()
            # 1) odometry prediction
            if args.sim:
                drive.advance(dt)
            d, dth = drive.odom_delta(dt)
            pose = compose(pose, d, dth)
            # 2) newest scan
            if args.sim:
                scan = world.scan()
            else:
                scan, last_stamp = lidar.get(last_stamp)
            if scan is not None:
                a, r = scan
                # 3) scan matching once the map has some structure
                if n_scans > 3:
                    pose, s = grid.match(pose, a, r)
                    match_scores.append(s)
                # 4) map update
                grid.update(pose, a, r)
                n_scans += 1
                # 5) decide
                v, w = brain.step(t, scan, pose)
            else:
                v, w = 0.0, 0.0              # no fresh scan: hold still (safe default)
            drive.set(v, w)
            if n_scans % 5 == 0:
                traj_est.append(pose[:2])
                if args.sim:
                    traj_true.append(tuple(world.pose[:2]))
            # 6) outputs
            if t - last_save > cfg["save_every_s"]:
                last_save = t
                grid.to_image(path=None, pose=pose).save(os.path.join(args.out, "map.png"))
                if args.pose_stream and args.sim:
                    # Estimated (scan-matched) pose only — never the sim
                    # ground truth. Consumed by rover_mission.sim_bridge.
                    with open(args.pose_stream, "a") as fh:
                        fh.write(json.dumps({
                            "t": round(t, 3), "ts": round(time.time(), 3),
                            "x": round(pose[0], 4),
                            "y": round(pose[1], 4), "theta": round(pose[2], 4),
                            "mode": brain.mode, "provenance": "SIM",
                        }) + "\n")
                if poster:
                    try:
                        poster.post(cfg["backend_url"].rstrip("/") + "/api/rover-pose",
                                    json={"pose": pose, "mode": brain.mode}, timeout=1)
                    except Exception:
                        pass
            t += dt
            if not (args.sim and args.fast):
                time.sleep(max(0.0, dt - (time.time() - loop_start)))
    except KeyboardInterrupt:
        pass
    finally:
        drive.stop()

    # ---- summary
    save_report(grid, pose, traj_est, traj_true, brain, os.path.join(args.out, "run_map.png"))
    g, cres = grid.nav_grid()
    vis = grid.visits
    k = grid.cres / cres
    import numpy as np
    ys, xs = np.nonzero(g == 0)
    seen = vis[np.minimum((ys / k).astype(int), vis.shape[0] - 1), np.minimum((xs / k).astype(int), vis.shape[1] - 1)] > 0
    summary = {
        "coverage_pct": round(100.0 * seen.mean(), 1) if len(seen) else 0.0,
        "sim_seconds": round(t, 1),
        "wall_seconds": round(time.time() - t_wall0, 1),
        "final_mode": brain.mode,
        "mode_changes": brain.log,
        "checkpoints": checkpoints,
        "distance_m": round(brain.travelled, 2),
        "map_cells_known": int(((grid.lo > 0.6) | (grid.lo < -0.6)).sum()),
    }
    if args.sim:
        tx, ty, tth = world.pose
        summary.update({
            "true_pose": [round(tx, 2), round(ty, 2), round(math.degrees(tth) % 360, 1)],
            "estimated_pose": [round(pose[0], 2), round(pose[1], 2), round(math.degrees(pose[2]) % 360, 1)],
            "pose_error_m": round(math.hypot(tx - pose[0], ty - pose[1]), 3),
            "collisions": world.collisions,
        })
    json.dump(summary, open(os.path.join(args.out, "summary.json"), "w"), indent=2)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
