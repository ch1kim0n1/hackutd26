from setuptools import find_packages, setup

package_name = "ms200_driver"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages",
         ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", ["launch/ms200.launch.py"]),
        ("share/" + package_name + "/rviz", ["rviz/ms200.rviz"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Sentinel Hive Team B",
    maintainer_email="team@sentinel-hive.local",
    description="ORADAR MS200 2D LiDAR ROS 2 driver",
    license="Apache-2.0",
    extras_require={"test": ["pytest"]},
    entry_points={
        "console_scripts": [
            "ms200_driver_node = ms200_driver.ms200_driver_node:main",
        ],
    },
)
