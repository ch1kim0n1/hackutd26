#include "rover_controller.h"

#include <cmath>
#include <cstdlib>

namespace rover {
namespace {

CommandResult reject(const char* reason) {
  CommandResult r;
  r.accepted = false;
  r.reason = reason;
  return r;
}

CommandResult accept() {
  CommandResult r;
  r.accepted = true;
  return r;
}

// mm/s per side for a turn rate in deg/s on this track width.
int32_t turnSideSpeed(int32_t rateDps, float trackWidthMm) {
  double radps = static_cast<double>(rateDps) * M_PI / 180.0;
  return static_cast<int32_t>(radps * trackWidthMm * 0.5);
}

} // namespace

RoverController::RoverController(Hal& hal, RoverConfig cfg)
    : hal_(hal), cfg_(cfg) {
  hal_.setMotorsEnabled(true);
  hal_.setMotorSpeedMmps(0, 0);
  hal_.encodersReset();
  lastLeftCounts_ = hal_.encoderCountsLeft();
  lastRightCounts_ = hal_.encoderCountsRight();
}

CommandResult RoverController::handleCommand(const CommandMsg& cmd) {
  switch (cmd.intent) {
    case Intent::kPing:
      return accept();

    case Intent::kEstopClear: {
      if (hal_.estopActive()) return reject("estop_active");
      estopLatch_ = 0;
      if (state_ == RoverState::kEstopped) {
        state_ = RoverState::kIdle;
        fault_ = FaultCode::kNone;
      }
      halt();
      refreshLed();
      return accept();
    }

    case Intent::kZeroOdometry:
      hal_.encodersReset();
      lastLeftCounts_ = hal_.encoderCountsLeft();
      lastRightCounts_ = hal_.encoderCountsRight();
      odomDistMm_ = 0;
      headingRad_ = 0.0;
      poseXmm_ = 0.0;
      poseYmm_ = 0.0;
      return accept();

    case Intent::kStop: {
      driving_ = false;
      cmdDeadlineMs_ = 0;
      if (state_ == RoverState::kDriving || state_ == RoverState::kFault) {
        state_ = RoverState::kIdle;
      }
      if (fault_ == FaultCode::kWatchdogTimeout ||
          fault_ == FaultCode::kCommandRejected) {
        fault_ = FaultCode::kNone;
      }
      setTarget(0, 0);
      refreshLed();
      return accept();
    }

    case Intent::kSetParams: {
      if (cmd.maxSpeedMmps > 0 && cmd.maxSpeedMmps <= 500) {
        cfg_.maxSpeedMmps = cmd.maxSpeedMmps;
      }
      if (cmd.obstacleMm >= 50 && cmd.obstacleMm <= 1000) {
        cfg_.obstacleStopMm = static_cast<uint16_t>(cmd.obstacleMm);
      }
      if (cmd.obstacleResumeMm >= 80 && cmd.obstacleResumeMm <= 1200) {
        cfg_.obstacleResumeMm = static_cast<uint16_t>(cmd.obstacleResumeMm);
      }
      if (cmd.maxTurnRateDps > 0 && cmd.maxTurnRateDps <= 180) {
        cfg_.maxTurnRateDps = cmd.maxTurnRateDps;
      }
      return accept();
    }

    case Intent::kForward:
    case Intent::kBackward:
    case Intent::kTurnLeft:
    case Intent::kTurnRight: {
      if (hal_.estopActive() || state_ == RoverState::kEstopped) {
        return reject("estop");
      }
      if (state_ == RoverState::kObstacleHold) return reject("obstacle");
      if (fault_ == FaultCode::kSensorFault) return reject("sensor_fault");

      // Speed/rate validation — reject rather than silently clamp.
      if (cmd.intent == Intent::kForward || cmd.intent == Intent::kBackward) {
        if (cmd.speedMmps > cfg_.maxSpeedMmps) return reject("speed_cap");
      } else {
        if (cmd.rateDps > cfg_.maxTurnRateDps) return reject("rate_cap");
      }

      uint32_t ttl = cmd.ttlMs ? cmd.ttlMs : cfg_.defaultTtlMs;
      if (ttl < 50 || ttl > 5000) return reject("ttl_range");

      int32_t left = 0, right = 0;
      int32_t speed = cmd.speedMmps;
      int32_t side = turnSideSpeed(cmd.rateDps, cfg_.trackWidthMm);
      if (side > cfg_.maxSpeedMmps) side = cfg_.maxSpeedMmps;
      switch (cmd.intent) {
        case Intent::kForward:  left = speed;  right = speed;  break;
        case Intent::kBackward: left = -speed; right = -speed; break;
        // CCW (left) turn: right side drives forward, left reverses.
        case Intent::kTurnLeft:  left = -side; right = side;  break;
        // CW (right) turn: left side drives forward, right reverses.
        case Intent::kTurnRight: left = side;  right = -side; break;
        default: break;
      }

      driving_ = true;
      state_ = RoverState::kDriving;
      fault_ = FaultCode::kNone;
      setTarget(left, right);
      cmdDeadlineMs_ = hal_.nowMs() + ttl;
      refreshLed();
      return accept();
    }

    case Intent::kUnknown:
    default:
      return reject("unknown_intent");
  }
}

void RoverController::setTarget(int32_t leftMmps, int32_t rightMmps) {
  targetLeftMmps_ = leftMmps;
  targetRightMmps_ = rightMmps;
}

void RoverController::halt() {
  driving_ = false;
  setTarget(0, 0);
}

void RoverController::enterFault(FaultCode f) {
  state_ = RoverState::kFault;
  fault_ = f;
  halt();
  curLeftMmps_ = 0;
  curRightMmps_ = 0;
  hal_.setMotorsEnabled(false); // STBY low — removes driver output
  refreshLed();
}

void RoverController::tick() {
  uint32_t now = hal_.nowMs();
  uint32_t dtMs = cfg_.tickMs;

  // --- 1. Physical E-stop: highest priority, checked every tick. ---
  bool estop = hal_.estopActive();
  if (estop) {
    estopWasActive_ = true;
    estopLatch_ = now;
    curLeftMmps_ = 0;
    curRightMmps_ = 0;
    hal_.setMotorSpeedMmps(0, 0);
    hal_.setMotorsEnabled(false);
    state_ = RoverState::kEstopped;
    fault_ = FaultCode::kEstop;
    refreshLed();
    updateOdometry();
    return;
  }
  if (estopWasActive_ && state_ == RoverState::kEstopped) {
    // Button released but latch held until explicit estop_clear command.
    curLeftMmps_ = 0;
    curRightMmps_ = 0;
    hal_.setMotorSpeedMmps(0, 0);
    hal_.setMotorsEnabled(false);
    refreshLed();
    updateOdometry();
    return;
  }
  estopWasActive_ = false;
  if (state_ != RoverState::kEstopped) {
    hal_.setMotorsEnabled(true);
  }

  // --- 2. Watchdog: motion command TTL expired -> stop motors. ---
  if (driving_ && now >= cmdDeadlineMs_) {
    enterFault(FaultCode::kWatchdogTimeout);
  }

  // --- 3. Obstacle monitoring (front every tick, rear every 4th). ---
  if (state_ != RoverState::kEstopped && state_ != RoverState::kFault) {
    updateObstacle();
  }

  // --- 4. Ramp current speeds toward targets. ---
  float dtSec = dtMs / 1000.0f;
  auto ramp = [&](int32_t cur, int32_t tgt) {
    int32_t delta = tgt - cur;
    if (delta == 0) return cur;
    int32_t rate = (delta > 0 ? cfg_.maxAccelMmpsPerSec : cfg_.maxDecelMmpsPerSec);
    int32_t limit = static_cast<int32_t>(rate * dtSec);
    if (limit < 1) limit = 1;
    if (delta > limit) return cur + limit;
    if (delta < -limit) return cur - limit;
    return tgt;
  };
  // Motors enabled only in states that may legitimately drive. STBY stays
  // low through estop latch and fault until a new valid command/state change.
  bool mayDrive = (state_ == RoverState::kIdle || state_ == RoverState::kDriving ||
                   state_ == RoverState::kObstacleHold) && !obstacleActive_;
  hal_.setMotorsEnabled(mayDrive);
  if (mayDrive) {
    curLeftMmps_ = ramp(curLeftMmps_, targetLeftMmps_);
    curRightMmps_ = ramp(curRightMmps_, targetRightMmps_);
    hal_.setMotorSpeedMmps(curLeftMmps_, curRightMmps_);
  } else {
    curLeftMmps_ = 0;
    curRightMmps_ = 0;
    hal_.setMotorSpeedMmps(0, 0);
  }

  updateOdometry();
  refreshLed();
}

void RoverController::updateObstacle() {
  uint16_t d = 0;
  tofTickDiv_++;

  // Front ToF every tick; rear every 4th tick (VL53L1X budget ~33 ms).
  if (hal_.tofReadMm(0, d)) {
    distFrontMm_ = d;
    frontValid_ = true;
    frontFailStreak_ = 0;
  } else {
    frontValid_ = false;
    if (++frontFailStreak_ >= cfg_.tofFailLimit) {
      enterFault(FaultCode::kSensorFault);
      return;
    }
  }

  if (cfg_.rearTofEnabled && (tofTickDiv_ & 3) == 0) {
    if (hal_.tofReadMm(1, d)) {
      distRearMm_ = d;
      rearValid_ = true;
      rearFailStreak_ = 0;
    } else {
      rearValid_ = false;
      if (++rearFailStreak_ >= cfg_.tofFailLimit) {
        enterFault(FaultCode::kSensorFault);
        return;
      }
    }
  } else if (!cfg_.rearTofEnabled) {
    rearValid_ = false;
  }

  bool frontHit = frontValid_ && distFrontMm_ < cfg_.obstacleStopMm;
  bool rearHit = cfg_.rearTofEnabled && rearValid_ && distRearMm_ < cfg_.obstacleStopMm;
  bool frontClear = frontValid_ && distFrontMm_ > cfg_.obstacleResumeMm;
  bool rearClear = !cfg_.rearTofEnabled || (rearValid_ && distRearMm_ > cfg_.obstacleResumeMm);

  if (state_ == RoverState::kObstacleHold) {
    if (frontClear && rearClear) {
      state_ = RoverState::kIdle;
      fault_ = FaultCode::kNone;
      obstacleActive_ = false;
    }
    return;
  }

  if ((frontHit || rearHit) &&
      (state_ == RoverState::kDriving || targetLeftMmps_ != 0 || targetRightMmps_ != 0)) {
    enterObstacleHold();
  }
}

void RoverController::enterObstacleHold() {
  state_ = RoverState::kObstacleHold;
  fault_ = FaultCode::kObstacle;
  obstacleActive_ = true;
  halt(); // ramp to zero; stays held until path clears + new command
  refreshLed();
}

void RoverController::updateOdometry() {
  int32_t l = hal_.encoderCountsLeft();
  int32_t r = hal_.encoderCountsRight();
  int32_t dl = l - lastLeftCounts_;
  int32_t dr = r - lastRightCounts_;
  lastLeftCounts_ = l;
  lastRightCounts_ = r;

  double dlMm = static_cast<double>(dl) * cfg_.encoderMmPerCount;
  double drMm = static_cast<double>(dr) * cfg_.encoderMmPerCount;
  double distMm = (dlMm + drMm) * 0.5;
  odomDistMm_ += static_cast<int64_t>(distMm);
  headingRad_ += (drMm - dlMm) / cfg_.trackWidthMm;
  poseXmm_ += distMm * std::cos(headingRad_);
  poseYmm_ += distMm * std::sin(headingRad_);
}

void RoverController::refreshLed() {
  uint8_t pat = kLedOff;
  switch (state_) {
    case RoverState::kIdle: pat = kLedIdle; break;
    case RoverState::kDriving: pat = kLedDriving; break;
    case RoverState::kEstopped: pat = kLedEstop; break;
    case RoverState::kObstacleHold: pat = kLedObstacle; break;
    case RoverState::kFault: pat = kLedFault; break;
  }
  hal_.setLed(pat);
}

TelemetryMsg RoverController::telemetry() const {
  TelemetryMsg t;
  t.seq = ++telemetrySeqCounter_;
  t.uptimeMs = hal_.nowMs();
  t.state = toString(state_);
  t.vLeftMmps = curLeftMmps_;
  t.vRightMmps = curRightMmps_;
  t.odomDistMm = static_cast<int32_t>(odomDistMm_);
  t.odomHeadingRad = static_cast<float>(headingRad_);
  t.poseXmm = static_cast<float>(poseXmm_);
  t.poseYmm = static_cast<float>(poseYmm_);
  t.distFrontMm = frontValid_ ? static_cast<int32_t>(distFrontMm_) : -1;
  t.distRearMm = rearValid_ ? static_cast<int32_t>(distRearMm_) : -1;
  t.estop = state_ == RoverState::kEstopped || fault_ == FaultCode::kEstop;
  t.obstacle = obstacleActive_ || state_ == RoverState::kObstacleHold;
  t.fault = toString(fault_);
  switch (state_) {
    case RoverState::kIdle: t.ledPattern = kLedIdle; break;
    case RoverState::kDriving: t.ledPattern = kLedDriving; break;
    case RoverState::kEstopped: t.ledPattern = kLedEstop; break;
    case RoverState::kObstacleHold: t.ledPattern = kLedObstacle; break;
    case RoverState::kFault: t.ledPattern = kLedFault; break;
  }
  return t;
}

void RoverController::currentSpeeds(int32_t& leftMmps, int32_t& rightMmps) const {
  leftMmps = curLeftMmps_;
  rightMmps = curRightMmps_;
}

} // namespace rover
