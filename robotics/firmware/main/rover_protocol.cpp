#include "rover_protocol.h"

#include <cstdlib>

#include "rover_types.h"

namespace rover {
namespace {

Intent intentFromString(const std::string& s) {
  if (s == "forward") return Intent::kForward;
  if (s == "backward") return Intent::kBackward;
  if (s == "turn_left") return Intent::kTurnLeft;
  if (s == "turn_right") return Intent::kTurnRight;
  if (s == "stop") return Intent::kStop;
  if (s == "zero_odometry") return Intent::kZeroOdometry;
  if (s == "estop_clear") return Intent::kEstopClear;
  if (s == "set_params") return Intent::kSetParams;
  if (s == "ping") return Intent::kPing;
  return Intent::kUnknown;
}

int32_t getI32(const json::Value& obj, const char* key, int32_t fallback, bool& present) {
  const json::Value* v = obj.find(key);
  if (!v || v->type != json::Value::Type::kNumber) { present = false; return fallback; }
  present = true;
  return static_cast<int32_t>(v->number);
}

uint32_t getU32(const json::Value& obj, const char* key, uint32_t fallback) {
  const json::Value* v = obj.find(key);
  if (!v || v->type != json::Value::Type::kNumber) return fallback;
  return static_cast<uint32_t>(v->number);
}

} // namespace

bool parseCommand(const std::string& line, CommandMsg& out) {
  json::Value root;
  if (!json::parse(line, root)) return false;
  if (root.type != json::Value::Type::kObject) return false;

  const json::Value* v = root.find("v");
  if (!v || v->type != json::Value::Type::kNumber ||
      static_cast<int>(v->number) != kProtocolVersion) {
    return false;
  }
  const json::Value* kind = root.find("kind");
  if (!kind || kind->type != json::Value::Type::kString || kind->asString() != "command") {
    return false;
  }
  const json::Value* id = root.find("cmd_id");
  if (!id || id->type != json::Value::Type::kString || id->asString().empty()) {
    return false;
  }
  const json::Value* intent = root.find("intent");
  if (!intent || intent->type != json::Value::Type::kString) return false;

  CommandMsg cmd;
  cmd.cmdId = id->asString();
  cmd.intent = intentFromString(intent->asString());
  if (cmd.intent == Intent::kUnknown) return false;
  cmd.ttlMs = getU32(root, "ttl_ms", 0);

  bool present = false;
  cmd.speedMmps = getI32(root, "speed_mmps", 0, present);
  cmd.rateDps = getI32(root, "rate_dps", 0, present);
  cmd.maxSpeedMmps = getI32(root, "max_speed_mmps", -1, present);
  cmd.obstacleMm = getI32(root, "obstacle_mm", -1, present);
  cmd.obstacleResumeMm = getI32(root, "obstacle_resume_mm", -1, present);
  cmd.maxTurnRateDps = getI32(root, "max_turn_rate_dps", -1, present);

  // Motion intents require a positive speed field of the right kind.
  switch (cmd.intent) {
    case Intent::kForward:
    case Intent::kBackward:
      if (cmd.speedMmps <= 0) return false;
      break;
    case Intent::kTurnLeft:
    case Intent::kTurnRight:
      if (cmd.rateDps <= 0) return false;
      break;
    default:
      break;
  }
  out = std::move(cmd);
  return true;
}

std::string serializeAck(const std::string& cmdId, const CommandResult& result) {
  json::Value root = json::Value::makeObject();
  root.set("v", json::Value::makeNumber(kProtocolVersion));
  root.set("kind", json::Value::makeString("ack"));
  root.set("cmd_id", json::Value::makeString(cmdId));
  root.set("accepted", json::Value::makeBool(result.accepted));
  if (!result.accepted && !result.reason.empty()) {
    root.set("reason", json::Value::makeString(result.reason));
  }
  return json::serialize(root);
}

std::string serializeTelemetry(const TelemetryMsg& t) {
  json::Value root = json::Value::makeObject();
  root.set("v", json::Value::makeNumber(kProtocolVersion));
  root.set("kind", json::Value::makeString("telemetry"));
  root.set("seq", json::Value::makeNumber(t.seq));
  root.set("uptime_ms", json::Value::makeNumber(t.uptimeMs));
  root.set("state", json::Value::makeString(t.state));
  root.set("v_left_mmps", json::Value::makeNumber(t.vLeftMmps));
  root.set("v_right_mmps", json::Value::makeNumber(t.vRightMmps));
  root.set("odom_dist_mm", json::Value::makeNumber(t.odomDistMm));
  root.set("odom_heading_rad", json::Value::makeNumber(t.odomHeadingRad));
  root.set("pose_x_mm", json::Value::makeNumber(t.poseXmm));
  root.set("pose_y_mm", json::Value::makeNumber(t.poseYmm));
  root.set("dist_front_mm", json::Value::makeNumber(t.distFrontMm));
  root.set("dist_rear_mm", json::Value::makeNumber(t.distRearMm));
  root.set("estop", json::Value::makeBool(t.estop));
  root.set("obstacle", json::Value::makeBool(t.obstacle));
  root.set("fault", json::Value::makeString(t.fault));
  root.set("led", json::Value::makeNumber(t.ledPattern));
  return json::serialize(root);
}

} // namespace rover
