#pragma once
// Serial line protocol between Pi (mission runtime) and ESP32 (motor
// controller). One compact JSON object per line, '\n' terminated.
//
// Pi -> ESP32 command:
//   {"v":1,"kind":"command","cmd_id":"c-1042","intent":"forward",
//    "speed_mmps":200,"ttl_ms":500}
//   intents: forward | backward | turn_left | turn_right | stop |
//            zero_odometry | estop_clear | set_params | ping
//   turn intents use "rate_dps" instead of "speed_mmps".
//   set_params may carry any of: max_speed_mmps, obstacle_mm,
//            obstacle_resume_mm, max_turn_rate_dps
//
// ESP32 -> Pi:
//   {"v":1,"kind":"ack","cmd_id":"c-1042","accepted":true}
//   {"v":1,"kind":"ack","cmd_id":"c-1042","accepted":false,"reason":"..."}
//   {"v":1,"kind":"telemetry","seq":42,...}  (see TelemetryMsg)
//
// Contract basis: docs/02 "command ID, motor intent, expiry, acknowledgement
// and error status"; docs/04 mission expiry is enforced again on the Pi.

#include <cstdint>
#include <string>

#include "rover_json.h"

namespace rover {

enum class Intent : uint8_t {
  kForward,
  kBackward,
  kTurnLeft,
  kTurnRight,
  kStop,
  kZeroOdometry,
  kEstopClear,
  kSetParams,
  kPing,
  kUnknown,
};

struct CommandMsg {
  std::string cmdId;
  Intent intent = Intent::kUnknown;
  int32_t speedMmps = 0;   // forward/backward
  int32_t rateDps = 0;     // turn_left/turn_right
  uint32_t ttlMs = 0;      // 0 -> controller default
  // set_params overrides (-1 = absent)
  int32_t maxSpeedMmps = -1;
  int32_t obstacleMm = -1;
  int32_t obstacleResumeMm = -1;
  int32_t maxTurnRateDps = -1;
};

struct CommandResult {
  bool accepted = false;
  std::string reason; // empty when accepted
};

// Parses one command line. Returns false on malformed JSON or schema
// violations (bad v/kind, missing cmd_id, unknown intent, bad types).
bool parseCommand(const std::string& line, CommandMsg& out);

// ack line for a command result.
std::string serializeAck(const std::string& cmdId, const CommandResult& result);

struct TelemetryMsg {
  uint32_t seq = 0;
  uint32_t uptimeMs = 0;
  const char* state = "idle";
  int32_t vLeftMmps = 0;
  int32_t vRightMmps = 0;
  int32_t odomDistMm = 0;
  float odomHeadingRad = 0.0f;
  float poseXmm = 0.0f;
  float poseYmm = 0.0f;
  int32_t distFrontMm = -1; // -1 = no valid reading
  int32_t distRearMm = -1;
  bool estop = false;
  bool obstacle = false;
  const char* fault = "none";
  uint8_t ledPattern = 0;
};

std::string serializeTelemetry(const TelemetryMsg& t);

} // namespace rover
