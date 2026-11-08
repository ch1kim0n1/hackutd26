import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg = get_package_share_directory("ms200_driver")
    return LaunchDescription([
        DeclareLaunchArgument("port", default_value="/dev/ttyUSB0"),
        DeclareLaunchArgument("baud", default_value="230400"),
        DeclareLaunchArgument("frame_id", default_value="ms200_laser"),
        DeclareLaunchArgument("topic", default_value="scan"),
        Node(
            package="ms200_driver",
            executable="ms200_driver_node",
            name="ms200_driver",
            parameters=[{
                "port": LaunchConfiguration("port"),
                "baud": LaunchConfiguration("baud"),
                "frame_id": LaunchConfiguration("frame_id"),
                "topic": LaunchConfiguration("topic"),
            }],
            output="screen",
        ),
        # RViz with the preconfigured LaserScan display
        Node(
            package="rviz2",
            executable="rviz2",
            name="rviz2",
            arguments=["-d", os.path.join(pkg, "rviz", "ms200.rviz")],
            output="screen",
        ),
    ])
