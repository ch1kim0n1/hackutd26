// Host unit tests for rover firmware core. Build: see test/CMakeLists.txt.
// Run: ./build/rover_tests  (or ctest)

#include <cmath>
#include <cstdio>
#include <cstring>
#include <string>

#include "../main/rover_controller.h"
#include "../main/rover_json.h"
#include "../main/rover_protocol.h"
#include "../main/rover_types.h"
#include "mock_hal.h"

using namespace rover;
using rover::test::MockHal;

static int g_failures = 0;
static int g_checks = 0;

#define CHECK(cond, msg) do { \
  ++g_checks; \
  if (!(cond)) { ++g_failures; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, msg); } \
} while (0)

// Advance controller+mock by n ticks of cfg.tickMs.
static void runTicks(MockHal& hal, RoverController& ctrl, int ticks) {
  for (int i = 0; i < ticks; ++i) {
    hal.advance(20);
    ctrl.tick();
    hal.simulateChassis();
  }
}

static CommandMsg mkCmd(Intent intent, const char* id, int32_t speed = 0,
                        int32_t rate = 0, uint32_t ttl = 0) {
  CommandMsg c;
  c.cmdId = id;
  c.intent = intent;
  c.speedMmps = speed;
  c.rateDps = rate;
  c.ttlMs = ttl;
  return c;
}

// ---------------- JSON codec ----------------
static void test_json() {
  json::Value v;
  CHECK(json::parse("{\"a\":1,\"b\":\"x\\n\",\"c\":[true,null,2.5]}", v), "json parse obj");
  CHECK(v.type == json::Value::Type::kObject, "json root object");
  const json::Value* a = v.find("a");
  CHECK(a && a->asNumber() == 1.0, "json number field");
  const json::Value* arr = v.find("c");
  CHECK(arr && arr->array.size() == 3, "json array len");
  CHECK(arr && arr->array[0].asBool() == true, "json bool elem");

  std::string s = json::serialize(v);
  json::Value v2;
  CHECK(json::parse(s, v2), "json round-trip parse");
  CHECK(v2.find("b")->asString() == "x\n", "json string escape round-trip");

  CHECK(!json::parse("{bad", v), "json rejects malformed");
  CHECK(!json::parse("[1,2", v), "json rejects truncated");
  CHECK(!json::parse("{\"a\":}", v), "json rejects bad value");
}

// ---------------- Protocol ----------------
static void test_protocol() {
  CommandMsg cmd;
  CHECK(parseCommand("{\"v\":1,\"kind\":\"command\",\"cmd_id\":\"c1\",\"intent\":\"forward\",\"speed_mmps\":200,\"ttl_ms\":500}", cmd),
        "parse forward cmd");
  CHECK(cmd.intent == Intent::kForward && cmd.speedMmps == 200 && cmd.ttlMs == 500, "cmd fields");

  CHECK(!parseCommand("{\"v\":2,\"kind\":\"command\",\"cmd_id\":\"c\",\"intent\":\"stop\"}", cmd), "reject bad version");
  CHECK(!parseCommand("{\"v\":1,\"kind\":\"telemetry\",\"cmd_id\":\"c\",\"intent\":\"stop\"}", cmd), "reject wrong kind");
  CHECK(!parseCommand("{\"v\":1,\"kind\":\"command\",\"intent\":\"stop\"}", cmd), "reject missing cmd_id");
  CHECK(!parseCommand("{\"v\":1,\"kind\":\"command\",\"cmd_id\":\"c\",\"intent\":\"warp\"}", cmd), "reject unknown intent");
  CHECK(!parseCommand("{\"v\":1,\"kind\":\"command\",\"cmd_id\":\"c\",\"intent\":\"forward\"}", cmd), "reject missing speed");
  CHECK(!parseCommand("not json", cmd), "reject non-json");

  CHECK(parseCommand("{\"v\":1,\"kind\":\"command\",\"cmd_id\":\"t\",\"intent\":\"turn_left\",\"rate_dps\":45}", cmd), "parse turn");
  CHECK(cmd.rateDps == 45, "turn rate field");

  std::string ack = serializeAck("c1", CommandResult{true, ""});
  CHECK(ack.find("\"accepted\":true") != std::string::npos, "ack accepted json");
  std::string nack = serializeAck("c2", CommandResult{false, "speed_cap"});
  CHECK(nack.find("speed_cap") != std::string::npos, "ack reason json");

  TelemetryMsg t;
  t.seq = 7; t.state = "driving"; t.vLeftMmps = 100;
  std::string tl = serializeTelemetry(t);
  json::Value tv;
  CHECK(json::parse(tl, tv), "telemetry parses as json");
  CHECK(tv.find("kind")->asString() == "telemetry", "telemetry kind");
  CHECK(tv.find("v_left_mmps")->asNumber() == 100.0, "telemetry speed field");
}

// ---------------- Controller: caps & ramp ----------------
static void test_caps_and_ramp() {
  MockHal hal;
  RoverController ctrl(hal);

  // Overspeed rejected.
  CommandResult r = ctrl.handleCommand(mkCmd(Intent::kForward, "c1", 999));
  CHECK(!r.accepted && r.reason == "speed_cap", "overspeed rejected");

  // At-cap accepted.
  r = ctrl.handleCommand(mkCmd(Intent::kForward, "c2", 250, 0, 5000));
  CHECK(r.accepted, "at-cap speed accepted");

  // Ramp: after 1 tick speed should be well below target (accel limit 400mm/s^2 @20ms = 8mm/s per tick).
  hal.advance(20); ctrl.tick();
  int32_t l, rr;
  ctrl.currentSpeeds(l, rr);
  CHECK(l > 0 && l < 250, "accel ramp limits initial speed");
  CHECK(l == rr, "forward drives both sides equal");

  // After enough ticks reaches target.
  runTicks(hal, ctrl, 60);
  ctrl.currentSpeeds(l, rr);
  CHECK(l == 250 && rr == 250, "ramp reaches target speed");

  // Turn produces differential speeds (left turn: right fwd, left rev).
  CommandResult tr = ctrl.handleCommand(mkCmd(Intent::kTurnLeft, "t1", 0, 30, 5000));
  CHECK(tr.accepted, "turn accepted");
  runTicks(hal, ctrl, 80);
  ctrl.currentSpeeds(l, rr);
  CHECK(rr > l, "turn_left right faster than left");
  CHECK(l < 0, "turn_left left reverses");

  // Overspeed turn rejected.
  tr = ctrl.handleCommand(mkCmd(Intent::kTurnRight, "t2", 0, 500));
  CHECK(!tr.accepted && tr.reason == "rate_cap", "turn rate cap enforced");
}

// ---------------- Watchdog (Pi cable disconnect) ----------------
static void test_watchdog() {
  MockHal hal;
  RoverController ctrl(hal);
  ctrl.handleCommand(mkCmd(Intent::kForward, "w1", 200, 0, 200)); // 200ms ttl
  runTicks(hal, ctrl, 10); // 200ms — at boundary
  ctrl.handleCommand(mkCmd(Intent::kForward, "w2", 200, 0, 300));
  // Advance past TTL without new command.
  runTicks(hal, ctrl, 20); // 400ms > 300ms ttl
  TelemetryMsg t = ctrl.telemetry();
  CHECK(std::string(t.fault) == "watchdog_timeout", "watchdog fault reported");
  int32_t l, r;
  ctrl.currentSpeeds(l, r);
  CHECK(l == 0 && r == 0, "watchdog stops motors");
  // Last motor command was zero.
  CHECK(hal.motorLog_.back().leftMmps == 0 && hal.motorLog_.back().rightMmps == 0,
        "watchdog zeroed motor output");
  // New command recovers.
  CommandResult rr = ctrl.handleCommand(mkCmd(Intent::kForward, "w3", 100));
  CHECK(rr.accepted, "command after watchdog accepted");
}

// ---------------- E-stop ----------------
static void test_estop() {
  MockHal hal;
  RoverController ctrl(hal);
  ctrl.handleCommand(mkCmd(Intent::kForward, "e1", 200, 0, 5000));
  runTicks(hal, ctrl, 40); // up to speed

  hal.setEstop(true);
  hal.advance(20); ctrl.tick();
  TelemetryMsg t = ctrl.telemetry();
  CHECK(t.state == std::string("estopped"), "estop state reported");
  CHECK(t.estop == true, "estop flag in telemetry");
  CHECK(t.fault == std::string("estop"), "estop fault code");
  int32_t l, r;
  ctrl.currentSpeeds(l, r);
  CHECK(l == 0 && r == 0, "estop zeroes speeds immediately");
  CHECK(hal.motorLog_.back().enabled == false, "estop disables motor driver (STBY)");

  // Motion commands rejected while estopped.
  CommandResult rej = ctrl.handleCommand(mkCmd(Intent::kForward, "e2", 100));
  CHECK(!rej.accepted && rej.reason == "estop", "drive rejected during estop");

  // Release button: still latched until estop_clear.
  hal.setEstop(false);
  runTicks(hal, ctrl, 5);
  t = ctrl.telemetry();
  CHECK(t.state == std::string("estopped"), "estop stays latched after release");

  // estop_clear while released -> accepted, back to idle.
  CommandResult clr = ctrl.handleCommand(mkCmd(Intent::kEstopClear, "e3"));
  CHECK(clr.accepted, "estop_clear accepted");
  runTicks(hal, ctrl, 2);
  t = ctrl.telemetry();
  CHECK(t.state == std::string("idle"), "idle after estop_clear");

  // estop_clear while still pressed -> rejected.
  hal.setEstop(true);
  hal.advance(20); ctrl.tick();
  CommandResult clr2 = ctrl.handleCommand(mkCmd(Intent::kEstopClear, "e4"));
  CHECK(!clr2.accepted && clr2.reason == "estop_active", "clear rejected while pressed");
}

// ---------------- Obstacle override ----------------
static void test_obstacle() {
  MockHal hal;
  RoverController ctrl(hal);
  hal.setTof(0, 400); // front clear
  hal.setTof(1, 400); // rear clear

  ctrl.handleCommand(mkCmd(Intent::kForward, "o1", 200, 0, 5000));
  runTicks(hal, ctrl, 30);
  int32_t l, r;
  ctrl.currentSpeeds(l, r);
  CHECK(l == 200, "driving before obstacle");

  // Obstacle appears 100mm ahead (< 150mm threshold).
  hal.setTof(0, 100);
  hal.advance(20); ctrl.tick();
  TelemetryMsg t = ctrl.telemetry();
  CHECK(t.state == std::string("obstacle_hold"), "obstacle_hold state");
  CHECK(t.obstacle == true, "obstacle flag set");
  CHECK(t.fault == std::string("obstacle"), "obstacle fault code");
  ctrl.currentSpeeds(l, r);
  CHECK(l == 0 && r == 0, "obstacle stops motors");

  // New commands rejected while held.
  CommandResult rej = ctrl.handleCommand(mkCmd(Intent::kForward, "o2", 100));
  CHECK(!rej.accepted && rej.reason == "obstacle", "drive rejected in obstacle hold");

  // Path clears beyond hysteresis (220mm) -> auto returns to idle.
  hal.setTof(0, 300);
  runTicks(hal, ctrl, 10);
  t = ctrl.telemetry();
  CHECK(t.state == std::string("idle"), "idle after obstacle clears");

  // New command accepted again.
  CommandResult ok = ctrl.handleCommand(mkCmd(Intent::kForward, "o3", 150, 0, 5000));
  CHECK(ok.accepted, "drive resumes after clear");
}

// ---------------- Sensor fault ----------------
static void test_sensor_fault() {
  MockHal hal;
  RoverController ctrl(hal);
  hal.setTofFail(0, true); // front ToF dead
  ctrl.handleCommand(mkCmd(Intent::kForward, "s1", 150));
  runTicks(hal, ctrl, 10); // 5 failures * 20ms -> fault
  TelemetryMsg t = ctrl.telemetry();
  CHECK(t.fault == std::string("sensor_fault"), "sensor fault after read failures");
  int32_t l, r;
  ctrl.currentSpeeds(l, r);
  CHECK(l == 0 && r == 0, "sensor fault stops motors");
  CommandResult rej = ctrl.handleCommand(mkCmd(Intent::kForward, "s2", 100));
  CHECK(!rej.accepted, "drive rejected while sensor fault latched");
}

// ---------------- Odometry ----------------
static void test_odometry() {
  MockHal hal;
  RoverController ctrl(hal);
  ctrl.handleCommand(mkCmd(Intent::kForward, "d1", 200, 0, 5000));
  runTicks(hal, ctrl, 50);
  ctrl.handleCommand(mkCmd(Intent::kStop, "d2"));
  TelemetryMsg t = ctrl.telemetry();
  CHECK(t.odomDistMm > 0, "odometry accumulates distance");
  CHECK(std::fabs(t.poseYmm) < 1.0, "straight drive stays on x axis");
  CHECK(t.poseXmm > 0, "forward drive moves +x");

  // Turn 90 deg-ish then drive: pose should curve.
  ctrl.handleCommand(mkCmd(Intent::kTurnLeft, "d3", 0, 60, 5000));
  runTicks(hal, ctrl, 100);
  ctrl.handleCommand(mkCmd(Intent::kStop, "d4"));
  t = ctrl.telemetry();
  CHECK(t.odomHeadingRad > 0.5, "left turn increases heading");

  // zero_odometry resets.
  ctrl.handleCommand(mkCmd(Intent::kZeroOdometry, "d5"));
  t = ctrl.telemetry();
  CHECK(t.odomDistMm == 0 && t.poseXmm == 0.0f && t.poseYmm == 0.0f, "zero_odometry resets pose");
}

// ---------------- set_params ----------------
static void test_set_params() {
  MockHal hal;
  RoverController ctrl(hal);
  CommandResult r = ctrl.handleCommand(mkCmd(Intent::kSetParams, "p1"));
  CHECK(r.accepted, "set_params accepted");

  // Lower the cap, then verify enforcement.
  CommandMsg sp;
  sp.cmdId = "p2";
  sp.intent = Intent::kSetParams;
  sp.maxSpeedMmps = 100;
  r = ctrl.handleCommand(sp);
  CHECK(r.accepted, "set_params speed accepted");
  CommandResult over = ctrl.handleCommand(mkCmd(Intent::kForward, "p3", 150));
  CHECK(!over.accepted && over.reason == "speed_cap", "lowered cap enforced");
  CommandResult ok = ctrl.handleCommand(mkCmd(Intent::kForward, "p4", 100, 0, 5000));
  CHECK(ok.accepted, "speed within new cap accepted");
}

// ---------------- Stop command ----------------
static void test_stop() {
  MockHal hal;
  RoverController ctrl(hal);
  ctrl.handleCommand(mkCmd(Intent::kForward, "st1", 200, 0, 5000));
  runTicks(hal, ctrl, 30);
  CommandResult r = ctrl.handleCommand(mkCmd(Intent::kStop, "st2"));
  CHECK(r.accepted, "stop accepted");
  runTicks(hal, ctrl, 30);
  TelemetryMsg t = ctrl.telemetry();
  CHECK(t.state == std::string("idle"), "idle after stop");
  int32_t l, rr;
  ctrl.currentSpeeds(l, rr);
  CHECK(l == 0 && rr == 0, "stop zeroes speeds");
}

int main() {
  test_json();
  test_protocol();
  test_caps_and_ramp();
  test_watchdog();
  test_estop();
  test_obstacle();
  test_sensor_fault();
  test_odometry();
  test_set_params();
  test_stop();

  std::printf("\n%d checks, %d failures\n", g_checks, g_failures);
  return g_failures == 0 ? 0 : 1;
}
