#include "rover_types.h"

namespace rover {

const char* toString(RoverState state) {
  switch (state) {
    case RoverState::kIdle: return "idle";
    case RoverState::kDriving: return "driving";
    case RoverState::kEstopped: return "estopped";
    case RoverState::kObstacleHold: return "obstacle_hold";
    case RoverState::kFault: return "fault";
  }
  return "unknown";
}

const char* toString(FaultCode fault) {
  switch (fault) {
    case FaultCode::kNone: return "none";
    case FaultCode::kWatchdogTimeout: return "watchdog_timeout";
    case FaultCode::kObstacle: return "obstacle";
    case FaultCode::kEstop: return "estop";
    case FaultCode::kSensorFault: return "sensor_fault";
    case FaultCode::kCommandRejected: return "command_rejected";
  }
  return "unknown";
}

} // namespace rover
