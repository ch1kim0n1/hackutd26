// Scripted simulator: drives RoverController through a patrol scenario on
// MockHal and prints JSON telemetry — reproducible evidence without hardware.
// Usage: ./rover_sim [ticks_per_phase]

#include <cstdio>
#include <cstdlib>
#include <string>

#include "../main/rover_controller.h"
#include "../main/rover_protocol.h"
#include "mock_hal.h"

using namespace rover;
using rover::test::MockHal;

static void emit(MockHal& hal, RoverController& ctrl, const char* tag) {
  TelemetryMsg t = ctrl.telemetry();
  std::string line = serializeTelemetry(t);
  std::printf("{\"scenario\":\"%s\",\"t_ms\":%u,%s\n", tag, hal.now_, line.c_str() + 1);
}

static void drive(MockHal& hal, RoverController& ctrl, Intent intent,
                  int32_t speed, int32_t rate, uint32_t ttlMs, int ticks) {
  CommandMsg c;
  c.cmdId = "sim";
  c.intent = intent;
  c.speedMmps = speed;
  c.rateDps = rate;
  c.ttlMs = ttlMs;
  CommandResult r = ctrl.handleCommand(c);
  std::printf("{\"cmd\":\"%s\",\"accepted\":%s,\"reason\":\"%s\"}\n",
              intent == Intent::kForward ? "forward" :
              intent == Intent::kTurnLeft ? "turn_left" : "other",
              r.accepted ? "true" : "false", r.reason.c_str());
  for (int i = 0; i < ticks; ++i) {
    hal.advance(20);
    ctrl.tick();
    hal.simulateChassis();
  }
}

int main(int argc, char** argv) {
  int ticks = argc > 1 ? std::atoi(argv[1]) : 50;
  MockHal hal;
  RoverConfig cfg;
  RoverController ctrl(hal, cfg);

  std::printf("{\"sim\":\"start\",\"note\":\"host mock, not physical hardware\"}\n");

  // 1. Patrol leg: forward 5 s equivalent.
  drive(hal, ctrl, Intent::kForward, 200, 0, 5000, ticks * 2);
  emit(hal, ctrl, "after_forward");

  // 2. Turn left, then forward again.
  drive(hal, ctrl, Intent::kTurnLeft, 0, 45, 5000, ticks);
  drive(hal, ctrl, Intent::kForward, 200, 0, 5000, ticks);
  emit(hal, ctrl, "after_turn_forward");

  // 3. Obstacle appears -> hold -> clears.
  hal.setTof(0, 100);
  hal.advance(20); ctrl.tick(); hal.simulateChassis();
  emit(hal, ctrl, "obstacle_hit");
  hal.setTof(0, 400);
  for (int i = 0; i < 10; ++i) { hal.advance(20); ctrl.tick(); hal.simulateChassis(); }
  emit(hal, ctrl, "obstacle_cleared");

  // 4. E-stop press/release/clear cycle.
  hal.setEstop(true);
  hal.advance(20); ctrl.tick(); hal.simulateChassis();
  emit(hal, ctrl, "estop_pressed");
  hal.setEstop(false);
  for (int i = 0; i < 5; ++i) { hal.advance(20); ctrl.tick(); hal.simulateChassis(); }
  CommandMsg clr; clr.cmdId = "sim-clr"; clr.intent = Intent::kEstopClear;
  ctrl.handleCommand(clr);
  for (int i = 0; i < 5; ++i) { hal.advance(20); ctrl.tick(); hal.simulateChassis(); }
  emit(hal, ctrl, "estop_cleared");

  // 5. Watchdog: command with short TTL, then silence.
  drive(hal, ctrl, Intent::kForward, 150, 0, 200, 2);
  for (int i = 0; i < 30; ++i) { hal.advance(20); ctrl.tick(); hal.simulateChassis(); }
  emit(hal, ctrl, "watchdog_timeout");

  std::printf("{\"sim\":\"done\"}\n");
  return 0;
}
