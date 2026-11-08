"""ms200_driver_node — publishes sensor_msgs/LaserScan from the MS200.

Params:
  port            serial device (default /dev/ttyUSB0)
  baud            UART baud (default 230400)
  frame_id        TF frame (default ms200_laser)
  topic           scan topic (default scan)
  publish_hz      timer rate (default 10.0; sensor scans 5-15 Hz)
  mount_offset_deg / clockwise — mechanical mounting correction

The node only republishes complete revolutions; partial scans are
skipped. ranges use inf for no-return (ROS convention).
"""
import math

import numpy as np

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan

from .lidar_serial import SerialLidar


class Ms200DriverNode(Node):
    def __init__(self):
        super().__init__("ms200_driver")
        self.declare_parameter("port", "/dev/ttyUSB0")
        self.declare_parameter("baud", 230400)
        self.declare_parameter("frame_id", "ms200_laser")
        self.declare_parameter("topic", "scan")
        self.declare_parameter("publish_hz", 10.0)
        self.declare_parameter("mount_offset_deg", 0.0)
        self.declare_parameter("clockwise", True)

        port = self.get_parameter("port").value
        baud = int(self.get_parameter("baud").value)
        self.frame_id = self.get_parameter("frame_id").value
        topic = self.get_parameter("topic").value
        hz = float(self.get_parameter("publish_hz").value)

        self.lidar = SerialLidar(
            port=port, baud=baud,
            mount_offset_deg=float(
                self.get_parameter("mount_offset_deg").value),
            clockwise=bool(self.get_parameter("clockwise").value))

        self.pub = self.create_publisher(LaserScan, topic, 10)
        self._last_stamp = 0.0
        self.create_timer(1.0 / max(hz, 0.1), self._tick)
        self.get_logger().info(
            f"ms200_driver publishing {topic} @ {hz}Hz "
            f"from {port}@{baud}")

    def _tick(self):
        scan, stamp = self.lidar.get(self._last_stamp)
        if scan is None:
            return
        self._last_stamp = stamp
        angles, ranges = scan
        msg = self._to_scan(angles, ranges, stamp)
        self.pub.publish(msg)

    def _to_scan(self, angles: np.ndarray, ranges: np.ndarray,
                 stamp: float) -> LaserScan:
        """Robot-frame (rad, m) -> LaserScan. ROS convention:
        angle 0 = +X, CCW positive — same as our assembler output."""
        order = np.argsort(angles)
        a = angles[order]
        r = ranges[order].astype(np.float32)
        n = len(r)
        msg = LaserScan()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.frame_id
        msg.angle_min = float(a[0]) if n else -math.pi
        msg.angle_max = float(a[-1]) if n else math.pi
        msg.angle_increment = (float(a[-1] - a[0]) / max(n - 1, 1)
                               if n > 1 else 0.0)
        msg.time_increment = 0.0
        msg.scan_time = 1.0 / 10.0
        msg.range_min = 0.05
        msg.range_max = 12.0
        msg.ranges = [float(x) if np.isfinite(x) else math.inf
                      for x in r]
        msg.intensities = []
        return msg


def main():
    rclpy.init()
    node = Ms200DriverNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
