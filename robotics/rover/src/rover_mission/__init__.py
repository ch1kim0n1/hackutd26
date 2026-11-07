"""SENTINEL HIVE rover mission runtime (Raspberry Pi side).

Drives the ESP32 motor controller through surveyed waypoints, fuses
encoder/AprilTag localization, captures hashed camera evidence, and emits
mission state telemetry. Contract: docs/04-DATA-AND-INTERFACES.md.
"""

__version__ = "0.1.0"
