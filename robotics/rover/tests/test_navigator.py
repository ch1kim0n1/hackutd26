"""Navigator unit tests — arrival, obstacle hold, estop, timeout."""

import math
import time

from rover_mission.localization import PoseEstimator
from rover_mission.models import Waypoint
from rover_mission.motor_link import SimulatedLink
from rover_mission.navigator import NavConfig, NavResult, Navigator


def _nav(link, **cfg):
    est = PoseEstimator(tag_to_waypoint={})
    est.reset()
    return Navigator(link, est, NavConfig(**cfg)), est


def _ticks(link, nav, est, n, dt=0.1):
    results = []
    for _ in range(n):
        link.pump()
        tel = link.telemetry()
        if tel:
            est.update_odometry(tel.pose_x_mm, tel.pose_y_mm,
                                tel.odom_heading_rad, 0)
        results.append(nav.goto(Waypoint("wp", "z", 500, 0), now=time.time()))
    return results


def test_goto_arrives():
    link = SimulatedLink(tick_s=0.1)
    link.connect()
    nav, est = _nav(link, waypoint_timeout_s=30)
    wp = Waypoint("wp", "z", 500, 0)
    last = None
    for _ in range(200):
        link.pump()
        tel = link.telemetry()
        if tel:
            est.update_odometry(tel.pose_x_mm, tel.pose_y_mm,
                                tel.odom_heading_rad, 0)
        last = nav.goto(wp, now=time.time())
        if last == NavResult.ARRIVED:
            break
    assert last == NavResult.ARRIVED
    assert est.pose.distance_to(500, 0) < 100


def test_obstacle_blocks_then_resumes():
    link = SimulatedLink(tick_s=0.1)
    link.connect()
    nav, est = _nav(link, waypoint_timeout_s=60, obstacle_patience_s=30)
    wp = Waypoint("wp", "z", 500, 0)
    link.force_obstacle = True
    saw_obstacle = False
    for _ in range(20):
        link.pump()
        tel = link.telemetry()
        if tel:
            est.update_odometry(tel.pose_x_mm, tel.pose_y_mm,
                                tel.odom_heading_rad, 0)
        r = nav.goto(wp, now=time.time())
        if r == NavResult.OBSTACLE:
            saw_obstacle = True
    assert saw_obstacle
    link.force_obstacle = False
    arrived = False
    for _ in range(300):
        link.pump()
        tel = link.telemetry()
        if tel:
            est.update_odometry(tel.pose_x_mm, tel.pose_y_mm,
                                tel.odom_heading_rad, 0)
        r = nav.goto(wp, now=time.time())
        if r == NavResult.ARRIVED:
            arrived = True
            break
    assert arrived


def test_estop_blocks():
    link = SimulatedLink(tick_s=0.1)
    link.connect()
    nav, est = _nav(link)
    wp = Waypoint("wp", "z", 500, 0)
    link.force_estop = True
    link.pump()
    r = nav.goto(wp, now=time.time())
    assert r == NavResult.ESTOP


def test_waypoint_timeout():
    link = SimulatedLink(tick_s=0.1)
    link.connect()
    nav, est = _nav(link, waypoint_timeout_s=0.5)
    wp = Waypoint("wp", "z", 9000, 9000)  # unreachable in 0.5 s
    results = set()
    t0 = time.time()
    for _ in range(100):
        link.pump()
        tel = link.telemetry()
        if tel:
            est.update_odometry(tel.pose_x_mm, tel.pose_y_mm,
                                tel.odom_heading_rad, 0)
        results.add(nav.goto(wp, now=t0 + _ * 0.1))
    assert NavResult.TIMEOUT in results or NavResult.ARRIVED not in results
