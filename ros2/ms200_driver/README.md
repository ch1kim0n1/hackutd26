# ms200_driver — ORADAR MS200 LiDAR ROS 2 driver

ROS 2 package publishing `sensor_msgs/LaserScan` from the ORADAR MS200
2D LiDAR (230400 baud UART via USB-UART adapter, LD06-style 47-byte
packets, CRC-8). Vendored serial reader lives in
`ms200_driver/lidar_serial.py` — same packet logic as
`autonomy/lidar.py`, self-contained for the ROS workspace.

## Hardware chain

MS200 -> 4-pin cable -> USB-UART adapter -> USB -> Kubuntu PC
(or rover companion computer). Sensor: 3.3 V UART, 5 V supply,
~4500 meas/s, 5-15 Hz, 12 m max range.

## Install (Kubuntu 24.04)

```bash
sudo apt update
sudo apt install -y ros-jazzy-desktop ros-jazzy-slam-toolbox \
  ros-jazzy-foxglove-bridge ros-dev-tools python3-serial python3-numpy
source /opt/ros/jazzy/setup.bash
```

Copy/symlink this directory into a colcon workspace:

```bash
mkdir -p ~/sentinel_ws/src && ln -s $PWD/ros2/ms200_driver ~/sentinel_ws/src/
cd ~/sentinel_ws && colcon build --packages-select ms200_driver
source install/setup.bash
```

User needs dialout: `sudo usermod -aG dialout $USER` (re-login).

## Run

```bash
ros2 launch ms200_driver ms200.launch.py port:=/dev/ttyUSB0
# or without RViz:
ros2 run ms200_driver ms200_driver_node --ros-args -p port:=/dev/ttyUSB0
```

Verify:

```bash
ros2 topic hz /scan
ros2 topic echo /scan --once
```

RViz2 opens automatically via the launch file with a preconfigured
LaserScan display (frame `ms200_laser`, topic `/scan`).

## Next stages (per bring-up plan)

1. **SLAM:** `ros2 launch slam_toolbox online_async_launch.py` with the
   scan remapped; needs odometry for a moving map.
2. **Foxglove:** `ros2 launch foxglove_bridge foxglove_bridge_launch.xml`
   then open app.foxglove.dev.
3. **Nav2:** only after localization works; not required for demo.

MS200 is single-plane 2D — it outlines surfaces at sensor height, it
does not produce 3D point clouds.

## Tests

`python3 -m pytest test` — packet CRC/parse, revolution assembly,
range filtering, mount offset. No ROS or hardware needed.
