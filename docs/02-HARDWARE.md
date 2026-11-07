# Hardware / Electrical / Procurement

## Parts
Rover: prebuilt encoder 2WD/4WD chassis, Raspberry Pi 5 with active cooling, ESP32 motor controller, motor-driver sized to stall current, two ToF distance sensors, CSI/USB camera, pan-tilt mast, visible LED ring, physical motor E-stop, protected battery, Pi-dedicated regulator, motor regulator, fuses, wiring. Three pucks: ESP32-S3 Wi-Fi scan/LED; ESP32 + magnetic reed cabinet switch/LED; ESP32 BLE test beacon observer/LED. Lab: two owned APs (authorized and unknown same-SSID), Linux test endpoint, dedicated firewall or manageable switch, AprilTags, physical cabinet mockup, independently hosted response-plane laptop/server. RF stretch: Kismet-compatible monitor-mode interface and suitable RTL-SDR with antenna for sub-GHz genuine spectrum capture.

## Estimated acquisition ranges (USD)
Pi/camera/cooling/storage 145–250; rover chassis 45–110; MCU+driver 25–60; ToF/mast/LED 35–100; protected power 40–110; pucks and enclosures 45–100; test lab 35–120; optional SDR 35–100; mounting/spares 30–75. Total rough 435–1,025, depending on owned equipment; do not treat as purchase quotes.

## Electrical integration
- Protected battery -> fuse/master switch -> two appropriately rated rails: Pi 5V according to actual board requirement and separate motor/servo rail.
- Motor rail includes an accessible physical E-stop; never power motors from Pi GPIO.
- Pi -> ESP32 over USB serial preferred, using command ID, motor intent, expiry, acknowledgement and error status.
- ESP32 -> motor driver PWM/direction; encoder pins -> ESP32 interrupts; ToF -> I2C with distinct addresses or XSHUT management.
- Camera CSI/USB -> Pi; pan-tilt servo on dedicated power. Common ground where required by control signal topology.
- ESP32 embedded firmware independently stops motors upon timeout, obstacle, E-stop or controller fault.
- Pin-by-pin wiring MUST be created after selecting actual purchased part numbers; do not publish imaginary pinouts.

## Bring-up gates
H01 multimeter-check rails with no Pi connected; H02 bench-test motor with wheels off ground; H03 prove E-stop removes motor energy; H04 disconnect Pi cable and verify motor watchdog; H05 validate obstacle stops; H06 calibrate AprilTag waypoint localization/encoders; H07 prove camera photo tagged to correct zone/time; H08 verify each puck event and device identity; H09 demonstrate five repeatable safe patrols; H10 test no Pi brownout under drive load.

## Required implementation artifacts
hardware-bom.csv with actual part numbers/quantities/owned-purchased/cost, part-specific wiring diagram, assembly photos, motor safety test report, firmware hashes, measured current and run time. These are not yet produced and block production assembly claims.
