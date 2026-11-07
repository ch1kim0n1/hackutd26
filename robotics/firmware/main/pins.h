#pragma once
// Pin map for the rover ESP32 — MUST match hardware/wiring-diagram.md §3.
// Re-verify against purchased board silkscreen before flashing (conflict log).

#include "driver/gpio.h"

namespace rover::pins {

// TB6612 motor drivers (VM on fused post-E-stop motor rail)
constexpr gpio_num_t kPwmA = GPIO_NUM_25;   // left side speed
constexpr gpio_num_t kAin1 = GPIO_NUM_26;   // left direction
constexpr gpio_num_t kAin2 = GPIO_NUM_27;
constexpr gpio_num_t kPwmB = GPIO_NUM_4;    // right side speed
constexpr gpio_num_t kBin1 = GPIO_NUM_5;
constexpr gpio_num_t kBin2 = GPIO_NUM_18;
constexpr gpio_num_t kStby = GPIO_NUM_33;   // both chips tied; HIGH = enabled

// Quadrature encoders, one per side (external 10k pull-ups per wiring doc)
constexpr gpio_num_t kEncL_A = GPIO_NUM_13;
constexpr gpio_num_t kEncL_B = GPIO_NUM_14;
constexpr gpio_num_t kEncR_A = GPIO_NUM_16;
constexpr gpio_num_t kEncR_B = GPIO_NUM_17;

// VL53L1X ToF on I2C (SDA=21, SCL=22), XSHUT for address assignment
constexpr gpio_num_t kI2cSda = GPIO_NUM_21;
constexpr gpio_num_t kI2cScl = GPIO_NUM_22;
constexpr gpio_num_t kTof0Xshut = GPIO_NUM_19;  // front
constexpr gpio_num_t kTof1Xshut = GPIO_NUM_20;  // rear (conflict C-1)

// E-stop NO contact -> status input; NC contact cuts motor rail in hardware
constexpr gpio_num_t kEstopStat = GPIO_NUM_34;  // input-only, active HIGH

// NeoPixel status ring data
constexpr gpio_num_t kLedData = GPIO_NUM_23;

constexpr uint8_t kI2cAddrFront = 0x52;
constexpr uint8_t kI2cAddrRear = 0x53;

} // namespace rover::pins
