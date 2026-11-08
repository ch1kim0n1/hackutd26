# Rover ground autonomy (2D LiDAR, Roomba-style + mapping)

Files
- run.py            main loop (10 Hz): odometry -> scan match -> map -> brain -> safety -> motors
- brain.py          behaviours: WALL_FOLLOW, EXPLORE (frontiers), PATROL (rack waypoints) / COVER, ESCAPE, BOUNCE, CHECKPOINT
- mapping.py        occupancy grid, correlative scan matching, coverage, frontiers, Dijkstra planner
- lidar.py          MS200 reader (serial LD06-style packets, or pipe from the vendor SDK), sector helper
- drive.py          TB6612 differential drive + dead reckoning
- sim.py            simulated data-center room, LiDAR and robot (for testing on a laptop)
- lidar_check.py    verify LiDAR data and mounting angle on the real car
- config.yaml       all settings (pins, speeds, distances, waypoints)

Quick start
1. Laptop test:   python3 run.py --sim --duration 240 --fast     -> out/run_map.png, out/summary.json
2. On the Pi:     python3 lidar_check.py   (box in front -> ~0 deg; fix mount_offset_deg / clockwise)
3. Wheels up:     sudo python3 run.py --duration 20   (check both wheels spin the right way; set invert_left/right)
4. Floor:         sudo python3 run.py
5. Patrol racks:  fill brain.waypoints with map coordinates read off out/map.png after an exploration run

Install packages through your safe-package-install.sh pipeline.

Mission service (inspect_cabinet, used by robotics/rover HttpHardwareTransport)
- mission_service.py  POST /missions, GET /missions/<id>, POST /missions/<id>/abort, POST /stop; loopback only
- mission.example.json  cabinet -> AprilTag id -> the one Pi it may probe; calibration knobs
- Start (camera service must be running on 127.0.0.1:18080):
    ROVER_AUTONOMY_TOKEN=<32+ chars> python3 mission_service.py --config ~/.config/blindspot-mission/mission.json
- Mac: ssh -L 18090:127.0.0.1:18090 david@<rover>, then
    ROVER_INSPECTOR=hardware ROVER_HARDWARE_TRANSPORT=http ROVER_AUTONOMY_URL=http://127.0.0.1:18090/missions ROVER_AUTONOMY_TOKEN=... ROVER_AUTONOMY_TIMEOUT_S=30
- motion_enabled=false: camera sweep, photo and Pi probe only, wheels never turn. Enable only after a wheels-up test.
- Tests: python3 -m pytest -q test_mission_service.py
