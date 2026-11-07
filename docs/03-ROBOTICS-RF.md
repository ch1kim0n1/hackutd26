# Robotics and RF Intelligence

## Rover behavior
Known office floor plan and marked waypoints (AprilTags + wheel odometry), capped indoor speed, obstacle stop, E-stop, local control timeout; NOT arbitrary SLAM. Authorized missions: patrol_route(route_id), inspect_zone(zone_id,waypoint_id), capture_photo(camera_id), wireless_rescan(zone_id), return_home, stop. No LLM raw PWM, arbitrary coordinates or shell.

States: queued, accepted, navigating, scanning, completed, failed, aborted, timed_out. Event includes mission ID, device ID, UTC timestamp, zone ID, pose confidence and reason. Operator has manual abort, and physical E-stop always overrides.

## Sensing
Puck A: ESP32-S3 2.4GHz Wi-Fi scan (SSID, BSSID, channel, RSSI, timestamp); repeated unknown-BSSID-on-known-SSID raises suspicion but is not proof of evil twin. Puck B: reed switch cabinet open/closed with debounce and authorized work window. Puck C: BLE observations ONLY from enrolled lab beacons; no people tracking. Kismet with supported capture adapters can add real Wi-Fi radio metadata and histories.

## IMPORTANT — RF waterfall correctness
**Wi-Fi channel activity view (P0):** real AP observation counts, RSSI distribution, channel heatmap; NOT a true spectrum waterfall.
**Actual RF waterfall (P1):** IQ samples from SDR supported frequency and antenna, windowed FFT producing center_frequency_hz, sample_rate_hz, fft_size, bin_width_hz, dbfs_bins, window, UTC time. Draw actual frequency axis, time axis, signal power. A generic RTL-SDR dongle is not a 2.4 GHz Wi-Fi receiver. Use a compatible authorized sub-GHz 433MHz test emitter if the hardware supports it. rtl_433 decodes specific ISM sensor protocols; it does not by itself provide universal SDR spectrum or 2.4GHz Wi-Fi.
Show LIVE, RECORDED or SYNTHETIC clearly. No deauth/jamming or third-party packet capture.

## Correlation
RF01 known SSID + unexpected BSSID in >=2 scans -> suspicious transmitter.
PHY01 contact switch opens outside maintenance -> physical anomaly.
CORR01 both in same zone within 120s -> incident candidate and rover inspection.
NET01 containment is successful only when test endpoint connectivity is independently verified.
Confidence reflects evidence quality, not model certainty; record alternatives, false positives and unknowns.

## Demo flow
Power on second test AP; first sensor detects unknown BSSID; cabinet switch opens; backend correlates; Nemotron requests rack inspection; rover navigates with AprilTag correction; captures hashed photo; dashboard presents live Wi-Fi channel activity and evidence; human approves bounded isolation of separate owned test endpoint; verify result.

## Measurements
Scan interval, RF observation delay p50/p95, waypoint error, collision count, photo timestamp accuracy, Wi-Fi scanning limitations, false alerts per ten controlled runs, real FFT provenance and antenna frequency.
