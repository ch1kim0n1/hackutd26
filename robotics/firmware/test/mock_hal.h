#pragma once
// Scriptable mock of the rover Hal for host tests.
// Virtual time, settable E-stop/ToF/encoder state; records motor commands.

#include <cstdint>
#include <vector>

#include "../main/rover_hal.h"

namespace rover::test {

struct MotorSample {
  uint32_t tMs;
  int32_t leftMmps;
  int32_t rightMmps;
  bool enabled;
};

class MockHal : public Hal {
public:
  uint32_t nowMs() const override { return now_; }
  void advance(uint32_t ms) { now_ += ms; }

  void setMotorSpeedMmps(int32_t leftMmps, int32_t rightMmps) override {
    lastLeftMmps_ = leftMmps;
    lastRightMmps_ = rightMmps;
    if (!motorLog_.empty() && motorLog_.back().tMs == now_ &&
        motorLog_.back().leftMmps == leftMmps && motorLog_.back().rightMmps == rightMmps &&
        motorLog_.back().enabled == enabled_) {
      return; // dedupe same-tick repeats
    }
    motorLog_.push_back({now_, leftMmps, rightMmps, enabled_});
  }

  void setMotorsEnabled(bool enabled) override {
    if (enabled_ != enabled) {
      enabled_ = enabled;
      motorLog_.push_back({now_, lastLeftMmps_, lastRightMmps_, enabled_});
    }
  }

  void setLed(uint8_t pattern) override { ledPattern_ = pattern; }
  bool estopActive() const override { return estop_; }
  void setEstop(bool active) { estop_ = active; }

  bool tofReadMm(uint8_t sensorIndex, uint16_t& distMm) override {
    if (tofFail_[sensorIndex]) return false;
    distMm = tofMm_[sensorIndex];
    tofReads_[sensorIndex]++;
    return true;
  }
  void setTof(uint8_t idx, uint16_t mm) { tofMm_[idx] = mm; }
  void setTofFail(uint8_t idx, bool fail) { tofFail_[idx] = fail; }
  uint32_t tofReadCount(uint8_t idx) const { return tofReads_[idx]; }

  void encodersReset() override {
    encL_ = 0;
    encR_ = 0;
  }
  int32_t encoderCountsLeft() const override { return encL_; }
  int32_t encoderCountsRight() const override { return encR_; }
  void setEncoderCounts(int32_t l, int32_t r) { encL_ = l; encR_ = r; }

  // Convenience: simulate the rover driving, updating encoders as if the
  // mock were a real chassis. Call once per 20 ms tick after ctrl.tick().
  // counts = mmps * dt(s) / encoderMmPerCount(0.05 mm/count).
  void simulateChassis() {
    encL_ += static_cast<int32_t>(lastLeftMmps_ * 0.02 / 0.05);
    encR_ += static_cast<int32_t>(lastRightMmps_ * 0.02 / 0.05);
  }

  uint32_t now_ = 0;
  bool estop_ = false;
  uint16_t tofMm_[2] = {400, 400};
  bool tofFail_[2] = {false, false};
  uint32_t tofReads_[2] = {0, 0};
  int32_t encL_ = 0;
  int32_t encR_ = 0;
  int32_t lastLeftMmps_ = 0;
  int32_t lastRightMmps_ = 0;
  bool enabled_ = true;
  uint8_t ledPattern_ = 0;
  std::vector<MotorSample> motorLog_;
};

} // namespace rover::test
