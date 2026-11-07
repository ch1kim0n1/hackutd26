#pragma once
// Shared wire/state types for the rover motor controller.
// Pure C++17 — no ESP-IDF or Arduino dependencies so the core builds and
// tests on the host (see test/). Pin map: hardware/wiring-diagram.md §3.

#include <cstdint>

namespace rover {

inline constexpr int kProtocolVersion = 1;

// Telemetry state machine. Mirrors docs/03 rover behavior states at the
// motion-primitive level (mission-level states live on the Pi).
enum class RoverState : uint8_t {
  kIdle = 0,        // powered, motors off, accepting commands
  kDriving = 1,     // executing a motion primitive under command TTL
  kEstopped = 2,    // physical E-stop active or latched pending estop_clear
  kObstacleHold = 3,// ToF obstacle inside stop threshold; awaits clear path
  kFault = 4,       // watchdog timeout, sensor fault, or rejected drive state
};

enum class FaultCode : uint8_t {
  kNone = 0,
  kWatchdogTimeout = 1, // no valid motion command before TTL expired
  kObstacle = 2,        // ToF reading inside obstacle threshold
  kEstop = 3,           // physical E-stop asserted
  kSensorFault = 4,     // repeated ToF/encoder read failures
  kCommandRejected = 5, // last command refused by safety checks
};

const char* toString(RoverState state);
const char* toString(FaultCode fault);

// LED patterns driven on GPIO23 NeoPixel ring (index = pattern id).
enum LedPattern : uint8_t {
  kLedOff = 0,
  kLedIdle = 1,     // slow green breathe
  kLedDriving = 2,  // solid green
  kLedFault = 3,    // blinking red
  kLedEstop = 4,    // solid red
  kLedObstacle = 5, // amber blink
};

} // namespace rover
