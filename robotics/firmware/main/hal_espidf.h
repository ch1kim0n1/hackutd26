#pragma once
// ESP-IDF implementation of the rover Hal interface.
// Maps mm/s speed targets to LEDC PWM duty on the TB6612 drivers, reads
// PCNT encoders, VL53L1X ToF over I2C, and the E-stop status GPIO.

#include "rover_hal.h"

#include "driver/gpio.h"
#include "esp_err.h"

namespace rover {

class EspIdfHal : public Hal {
public:
  // mmPerDuty calibration: measured top speed at 100% duty (H06 gate).
  explicit EspIdfHal(float maxSpeedMmpsAtFullDuty = 400.0f);
  ~EspIdfHal() override = default;

  esp_err_t init();   // call once from app_main before controller use
  void deinit();

  uint32_t nowMs() const override;
  void setMotorSpeedMmps(int32_t leftMmps, int32_t rightMmps) override;
  void setMotorsEnabled(bool enabled) override;
  void setLed(uint8_t pattern) override;
  bool estopActive() const override;
  bool tofReadMm(uint8_t sensorIndex, uint16_t& distMm) override;
  void encodersReset() override;
  int32_t encoderCountsLeft() const override;
  int32_t encoderCountsRight() const override;

private:
  void applyDirectionLeft(bool forward);
  void applyDirectionRight(bool forward);
  void setDutyLeft(uint32_t duty);
  void setDutyRight(uint32_t duty);

  float mmpsPerDuty_;
  bool enabled_ = false;
};

} // namespace rover
