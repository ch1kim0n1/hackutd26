// Rover firmware entry — ESP-IDF app.
// UART0 (USB serial) line protocol <-> RoverController @ ~50 Hz tick.
// Safety behavior lives entirely in rover_controller.cpp; this file only
// moves bytes and dispatches commands.

#include <cstdio>
#include <cstring>

#include "driver/gpio.h"
#include "driver/uart.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "hal_espidf.h"
#include "rover_config.h"
#include "rover_controller.h"
#include "rover_protocol.h"
#include "rover_types.h"

namespace {
constexpr const char* kTag = "rover_fw";
constexpr uart_port_t kUart = UART_NUM_0;
constexpr int kUartBaud = 115200;
constexpr int kUartBufSize = 1024;
constexpr size_t kLineMax = 512;
constexpr uint32_t kControlPeriodMs = 20;   // 50 Hz

EspIdfHal* g_hal = nullptr;
RoverController* g_ctrl = nullptr;

void uartInit() {
  uart_config_t cfg = {};
  cfg.baud_rate = kUartBaud;
  cfg.data_bits = UART_DATA_8_BITS;
  cfg.parity = UART_PARITY_DISABLE;
  cfg.stop_bits = UART_STOP_BITS_1;
  cfg.flow_ctrl = UART_HW_FLOWCTRL_DISABLE;
  cfg.source_clk = UART_SCLK_DEFAULT;
  ESP_ERROR_CHECK(uart_param_config(kUart, &cfg));
  ESP_ERROR_CHECK(uart_set_pin(kUart, GPIO_NUM_1, GPIO_NUM_3, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));
  ESP_ERROR_CHECK(uart_driver_install(kUart, kUartBufSize, 0, 0, nullptr, 0));
}

// Reads available UART bytes, splits on '\n', dispatches complete lines.
void pumpCommands() {
  static char line[kLineMax];
  static size_t len = 0;

  uint8_t buf[128];
  int n = uart_read_bytes(kUart, buf, sizeof(buf), 0);
  for (int i = 0; i < n; ++i) {
    char c = static_cast<char>(buf[i]);
    if (c == '\n' || c == '\r') {
      if (len > 0) {
        line[len] = '\0';
        rover::CommandMsg cmd;
        if (rover::parseCommand(line, cmd)) {
          rover::CommandResult res = g_ctrl->handleCommand(cmd);
          std::string ack = rover::serializeAck(cmd.cmdId, res);
          uart_write_bytes(kUart, ack.data(), ack.size());
          uart_write_bytes(kUart, "\n", 1);
        } else {
          // Malformed line: nack with empty cmd_id so Pi sees the rejection.
          std::string ack = rover::serializeAck("", rover::CommandResult{false, "malformed"});
          uart_write_bytes(kUart, ack.data(), ack.size());
          uart_write_bytes(kUart, "\n", 1);
        }
        len = 0;
      }
    } else if (len < kLineMax - 1) {
      line[len++] = c;
    } else {
      len = 0; // oversized line: drop and resync on next newline
    }
  }
}

} // namespace

extern "C" void app_main() {
  ESP_LOGI(kTag, "SENTINEL HIVE rover firmware v%d", rover::kProtocolVersion);

  uartInit();

  static EspIdfHal hal(400.0f); // mm/s at 100% duty — calibrate at H06
  if (hal.init() != ESP_OK) {
    ESP_LOGE(kTag, "HAL init failed");
    while (true) vTaskDelay(pdMS_TO_TICKS(1000));
  }

  static RoverConfig cfg;
  cfg.tickMs = kControlPeriodMs;
  static RoverController ctrl(hal, cfg);
  g_hal = &hal;
  g_ctrl = &ctrl;

  uint32_t lastTick = hal.nowMs();
  uint32_t lastTelemetry = 0;

  for (;;) {
    uint32_t now = hal.nowMs();
    if (now - lastTick >= kControlPeriodMs) {
      lastTick = now;
      ctrl.tick();
    }
    pumpCommands();
    if (now - lastTelemetry >= cfg.telemetryPeriodMs) {
      lastTelemetry = now;
      rover::TelemetryMsg t = ctrl.telemetry();
      std::string line = rover::serializeTelemetry(t);
      uart_write_bytes(kUart, line.data(), line.size());
      uart_write_bytes(kUart, "\n", 1);
    }
    vTaskDelay(pdMS_TO_TICKS(2));
  }
}
