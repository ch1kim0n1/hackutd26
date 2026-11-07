#pragma once
// Rover safety controller — pure logic, fully host-testable.
// Enforces, in order of precedence:
//   physical E-stop > ToF obstacle > command TTL watchdog > speed/turn caps
//   > accel/decel ramp > odometry.
// The ESP-IDF HAL (hal_espidf.cpp) and the host mock both sit behind Hal.

#include <cstdint>

#include "rover_config.h"
#include "rover_hal.h"
#include "rover_protocol.h"
#include "rover_types.h"

namespace rover {

class RoverController {
public:
  explicit RoverController(Hal& hal, RoverConfig cfg = {});

  // Execute one parsed command; returns ack payload for the Pi.
  CommandResult handleCommand(const CommandMsg& cmd);

  // Advance one control tick. Call every cfg.tickMs.
  void tick();

  TelemetryMsg telemetry() const;

  // Current effective (ramped) per-side speeds in mm/s.
  void currentSpeeds(int32_t& leftMmps, int32_t& rightMmps) const;

private:
  void setTarget(int32_t leftMmps, int32_t rightMmps);
  void halt();                       // ramp to zero without changing state
  void enterFault(FaultCode f);      // stop motors, latch fault state
  void enterObstacleHold();          // stop motors, hold until path clears
  void updateObstacle();
  void updateOdometry();
  void refreshLed();

  Hal& hal_;
  RoverConfig cfg_;

  RoverState state_ = RoverState::kIdle;
  FaultCode fault_ = FaultCode::kNone;
  uint32_t estopLatch_ = 0;          // uptime ms when estop last seen active
  bool estopWasActive_ = false;

  // Active motion command
  bool driving_ = false;
  uint32_t cmdDeadlineMs_ = 0;
  int32_t targetLeftMmps_ = 0;
  int32_t targetRightMmps_ = 0;
  int32_t curLeftMmps_ = 0;
  int32_t curRightMmps_ = 0;

  // Obstacle monitoring
  uint16_t distFrontMm_ = 0;
  uint16_t distRearMm_ = 0;
  bool frontValid_ = false;
  bool rearValid_ = false;
  bool obstacleActive_ = false;
  uint8_t frontFailStreak_ = 0;
  uint8_t rearFailStreak_ = 0;

  // Odometry
  int32_t lastLeftCounts_ = 0;
  int32_t lastRightCounts_ = 0;
  int64_t odomDistMm_ = 0;
  double headingRad_ = 0.0;
  double poseXmm_ = 0.0;
  double poseYmm_ = 0.0;

  mutable uint32_t telemetrySeqCounter_ = 0;
  uint8_t tofTickDiv_ = 0;
};

} // namespace rover
