#pragma once
// Hardware abstraction for the rover controller.
// Implemented by hal_espidf.cpp on target and mock_hal in test/ on host.
// All methods must be safe to call every control tick (~20 ms).

#include <cstdint>

namespace rover {

class Hal {
public:
  virtual ~Hal() = default;

  virtual uint32_t nowMs() const = 0;

  // Motor speed commands in mm/s per side (signed: + forward). The HAL maps
  // mm/s to PWM duty via its calibrated max speed. Called every tick with the
  // ramped speed; safe to call with 0,0 to hold still.
  virtual void setMotorSpeedMmps(int32_t leftMmps, int32_t rightMmps) = 0;

  // Master motor enable (TB6612 STBY). Held low on any fault/estop.
  virtual void setMotorsEnabled(bool enabled) = 0;

  virtual void setLed(uint8_t pattern) = 0;

  // Physical E-stop status input (GPIO34, active HIGH per wiring-diagram).
  virtual bool estopActive() const = 0;

  // ToF distance read. sensorIndex 0 = front, 1 = rear. Returns false on
  // I2C/timeout error; distMm is undefined then.
  virtual bool tofReadMm(uint8_t sensorIndex, uint16_t& distMm) = 0;

  virtual void encodersReset() = 0;
  // Cumulative encoder counts since reset (signed; direction per wiring).
  virtual int32_t encoderCountsLeft() const = 0;
  virtual int32_t encoderCountsRight() const = 0;
};

} // namespace rover
