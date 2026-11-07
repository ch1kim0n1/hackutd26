#pragma once
// Rover controller tuning. Defaults follow docs/03-ROBOTICS-RF.md and the
// docs/04 mission contract (max_speed_mps 0.25). encoderMmPerCount MUST be
// recalibrated during bring-up gate H06.

#include <cstdint>

namespace rover {

struct RoverConfig {
  uint32_t tickMs = 20;                // control loop period
  uint16_t defaultTtlMs = 500;         // TTL applied when command omits ttl_ms
  int32_t maxSpeedMmps = 250;          // absolute cap (0.25 m/s mission cap)
  int32_t maxAccelMmpsPerSec = 400;    // ramp-up slew limit
  int32_t maxDecelMmpsPerSec = 1500;   // ramp-down slew limit (faster stop)
  int32_t maxTurnRateDps = 90;         // rotation cap for turn primitives
  uint16_t obstacleStopMm = 150;       // ToF distance that triggers stop
  uint16_t obstacleResumeMm = 220;     // hysteresis before path counts as clear
  uint8_t tofFailLimit = 5;            // consecutive read errors -> sensor fault
  float trackWidthMm = 160.0f;         // wheel separation for turns/heading
  float encoderMmPerCount = 0.05f;     // H06 calibration placeholder
  uint16_t telemetryPeriodMs = 100;    // status line rate to Pi
  bool rearTofEnabled = true;          // rear sensor optional per build
};

} // namespace rover
