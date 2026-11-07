// ESP-IDF HAL for the rover controller. Target-only — not compiled by the
// host test build. Flash/bring-up pending physical hardware (H01-H10).

#include "hal_espidf.h"

#include <algorithm>
#include <cmath>

#include "driver/i2c_master.h"
#include "driver/ledc.h"
#include "driver/pcnt.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "pins.h"
#include "rover_types.h"

// VL53L1X driver: Pololu ESP-IDF component `vl53l1x` (see idf_component.yml).
#include "vl53l1x.h"

namespace rover {
namespace {
constexpr const char* kTag = "rover_hal";
constexpr ledc_mode_t kLedcMode = LEDC_LOW_SPEED_MODE;
constexpr ledc_timer_t kLedcTimer = LEDC_TIMER_0;
constexpr ledc_channel_t kChanA = LEDC_CHANNEL_0;
constexpr ledc_channel_t kChanB = LEDC_CHANNEL_1;
constexpr uint32_t kPwmFreqHz = 20000;
constexpr ledc_timer_bit_t kPwmBits = LEDC_TIMER_8_BIT; // 0-255 duty
constexpr uint32_t kDutyMax = 255;

// PCNT units: one quad-mode unit per side encoder.
constexpr pcnt_unit_t kPcntLeft = PCNT_UNIT_0;
constexpr pcnt_unit_t kPcntRight = PCNT_UNIT_1;
constexpr int32_t kPcntMaxCounts = 100000;

vl53l1x_t s_tof[2];
i2c_master_bus_handle_t s_i2cBus = nullptr;

void tofXshut(bool on) {
  gpio_set_level(pins::kTof0Xshut, on ? 1 : 0);
  gpio_set_level(pins::kTof1Xshut, on ? 1 : 0);
}

esp_err_t initPcnt(pcnt_unit_t unit, gpio_num_t pinA, gpio_num_t pinB) {
  pcnt_config_t cfg = {};
  cfg.unit = unit;
  cfg.channel[0].io_num = pinA;
  cfg.channel[0].pulse_gpio_num = pinB;
  cfg.channel[0].flags.io_loop_back = false;
  cfg.channel[0].flags.pull_up = true; // external 10k also fitted per wiring doc
  cfg.channel[1].io_num = pinB;
  cfg.channel[1].pulse_gpio_num = pinA;
  cfg.channel[1].flags.io_loop_back = false;
  cfg.channel[1].flags.pull_up = true;
  cfg.high_limit = kPcntMaxCounts;
  cfg.low_limit = -kPcntMaxCounts;
  esp_err_t err = pcnt_new_unit(&cfg);
  if (err != ESP_OK) return err;
  pcnt_glitch_filter_config_t filt = {};
  filt.max_glitch_ns = 1000;
  pcnt_unit_set_glitch_filter(unit, &filt);
  return pcnt_unit_enable(unit);
}

} // namespace

EspIdfHal::EspIdfHal(float maxSpeedMmpsAtFullDuty)
    : mmpsPerDuty_(maxSpeedMmpsAtFullDuty / (kDutyMax / 2.0f)) {}

uint32_t EspIdfHal::nowMs() const {
  return static_cast<uint32_t>(esp_timer_get_time() / 1000ULL);
}

esp_err_t EspIdfHal::init() {
  // --- GPIO: directions, STBY, E-stop, XSHUT, LED ---
  const gpio_num_t outs[] = {pins::kAin1, pins::kAin2, pins::kBin1, pins::kBin2,
                             pins::kStby, pins::kTof0Xshut, pins::kTof1Xshut,
                             pins::kLedData};
  for (gpio_num_t p : outs) {
    gpio_config_t io = {};
    io.pin_bit_mask = 1ULL << p;
    io.mode = GPIO_MODE_OUTPUT;
    io.pull_up_en = GPIO_PULLUP_DISABLE;
    io.pull_down_en = GPIO_PULLDOWN_DISABLE;
    io.intr_type = GPIO_INTR_DISABLE;
    gpio_config(&io);
  }
  gpio_set_level(pins::kStby, 0);
  gpio_set_level(pins::kAin1, 0);
  gpio_set_level(pins::kAin2, 0);
  gpio_set_level(pins::kBin1, 0);
  gpio_set_level(pins::kBin2, 0);
  gpio_set_level(pins::kTof0Xshut, 0);
  gpio_set_level(pins::kTof1Xshut, 0);

  gpio_config_t estop = {};
  estop.pin_bit_mask = 1ULL << pins::kEstopStat;
  estop.mode = GPIO_MODE_INPUT;
  estop.pull_up_en = GPIO_PULLUP_DISABLE;
  estop.pull_down_en = GPIO_PULLDOWN_ENABLE; // NO contact to 3V3
  estop.intr_type = GPIO_INTR_DISABLE;
  gpio_config(&estop);

  // --- LEDC PWM ---
  ledc_timer_config_t tcfg = {};
  tcfg.speed_mode = kLedcMode;
  tcfg.duty_resolution = kPwmBits;
  tcfg.timer_num = kLedcTimer;
  tcfg.freq_hz = kPwmFreqHz;
  tcfg.clk_cfg = LEDC_AUTO_CLK;
  ESP_ERROR_CHECK(ledc_timer_config(&tcfg));

  ledc_channel_config_t ch = {};
  ch.speed_mode = kLedcMode;
  ch.timer_sel = kLedcTimer;
  ch.duty = 0;
  ch.hpoint = 0;
  ch.intr_type = LEDC_INTR_DISABLE;
  ch.flags.output_invert = false;

  ch.channel = kChanA;
  ch.gpio_num = pins::kPwmA;
  ESP_ERROR_CHECK(ledc_channel_config(&ch));
  ch.channel = kChanB;
  ch.gpio_num = pins::kPwmB;
  ESP_ERROR_CHECK(ledc_channel_config(&ch));

  // --- PCNT encoders ---
  ESP_ERROR_CHECK(initPcnt(kPcntLeft, pins::kEncL_A, pins::kEncL_B));
  ESP_ERROR_CHECK(initPcnt(kPcntRight, pins::kEncR_A, pins::kEncR_B));

  // --- I2C bus + VL53L1X ToF pair ---
  i2c_master_bus_config_t buscfg = {};
  buscfg.i2c_port = I2C_NUM_0;
  buscfg.sda_io_num = pins::kI2cSda;
  buscfg.scl_io_num = pins::kI2cScl;
  buscfg.clk_source = I2C_CLK_SRC_DEFAULT;
  buscfg.glitch_ignore_cnt = 7;
  buscfg.flags.enable_internal_pullup = true;
  ESP_ERROR_CHECK(i2c_new_master_bus(&buscfg, &s_i2cBus));

  // Sequential XSHUT boot assigns 0x52 then 0x53 (wiring-diagram conflict C-1).
  tofXshut(false);
  vTaskDelay(pdMS_TO_TICKS(10));
  gpio_set_level(pins::kTof0Xshut, 1);
  vTaskDelay(pdMS_TO_TICKS(10));
  ESP_ERROR_CHECK(vl53l1x_init(&s_tof[0], s_i2cBus, pins::kI2cSda, pins::kI2cScl,
                                pins::kTof0Xshut, GPIO_NUM_NC, pins::kI2cAddrFront));
  gpio_set_level(pins::kTof1Xshut, 1);
  vTaskDelay(pdMS_TO_TICKS(10));
  esp_err_t err2 = vl53l1x_init(&s_tof[1], s_i2cBus, pins::kI2cSda, pins::kI2cScl,
                                pins::kTof1Xshut, GPIO_NUM_NC, pins::kI2cAddrRear);
  if (err2 != ESP_OK) {
    ESP_LOGW(kTag, "rear ToF init failed (%s); rear obstacle disabled", esp_err_to_name(err2));
  }
  vl53l1x_set_timing_budget_ms(&s_tof[0], 33);
  vl53l1x_set_timing_budget_ms(&s_tof[1], 33);
  vl53l1x_start_ranging(&s_tof[0]);
  vl53l1x_start_ranging(&s_tof[1]);

  ESP_LOGI(kTag, "rover HAL ready (mmps/duty=%.2f)", mmpsPerDuty_);
  return ESP_OK;
}

void EspIdfHal::deinit() {
  setMotorSpeedMmps(0, 0);
  setMotorsEnabled(false);
}

bool EspIdfHal::estopActive() const {
  return gpio_get_level(pins::kEstopStat) == 1;
}

void EspIdfHal::setMotorsEnabled(bool enabled) {
  enabled_ = enabled;
  gpio_set_level(pins::kStby, enabled ? 1 : 0);
}

void EspIdfHal::setDutyLeft(uint32_t duty) {
  ledc_set_duty(kLedcMode, kChanA, std::min(duty, kDutyMax));
  ledc_update_duty(kLedcMode, kChanA);
}

void EspIdfHal::setDutyRight(uint32_t duty) {
  ledc_set_duty(kLedcMode, kChanB, std::min(duty, kDutyMax));
  ledc_update_duty(kLedcMode, kChanB);
}

void EspIdfHal::applyDirectionLeft(bool forward) {
  // AIN1=forward, AIN2=reverse (per TB6612 truth table in wiring doc).
  gpio_set_level(pins::kAin1, forward ? 1 : 0);
  gpio_set_level(pins::kAin2, forward ? 0 : 1);
}

void EspIdfHal::applyDirectionRight(bool forward) {
  gpio_set_level(pins::kBin1, forward ? 1 : 0);
  gpio_set_level(pins::kBin2, forward ? 0 : 1);
}

void EspIdfHal::setMotorSpeedMmps(int32_t leftMmps, int32_t rightMmps) {
  auto apply = [&](int32_t mmps, void (EspIdfHal::*dirFn)(bool),
                   void (EspIdfHal::*dutyFn)(uint32_t)) {
    if (mmps == 0) {
      (this->*dutyFn)(0);
      return;
    }
    bool forward = mmps > 0;
    (this->*dirFn)(forward);
    float dutyF = std::min(std::fabs(static_cast<float>(mmps)) / mmpsPerDuty_,
                           static_cast<float>(kDutyMax));
    (this->*dutyFn)(static_cast<uint32_t>(dutyF));
  };
  apply(leftMmps, &EspIdfHal::applyDirectionLeft, &EspIdfHal::setDutyLeft);
  apply(rightMmps, &EspIdfHal::applyDirectionRight, &EspIdfHal::setDutyRight);
}

bool EspIdfHal::tofReadMm(uint8_t sensorIndex, uint16_t& distMm) {
  if (sensorIndex > 1) return false;
  uint16_t d = 0;
  vl53l1x_err_t err = vl53l1x_read(&s_tof[sensorIndex], &d, false);
  if (err != VL53L1X_ERR_NONE) return false;
  distMm = d;
  return true;
}

void EspIdfHal::encodersReset() {
  pcnt_unit_clear_count(kPcntLeft);
  pcnt_unit_clear_count(kPcntRight);
}

int32_t EspIdfHal::encoderCountsLeft() const {
  int cnt = 0;
  pcnt_unit_get_count(kPcntLeft, &cnt);
  return cnt;
}

int32_t EspIdfHal::encoderCountsRight() const {
  int cnt = 0;
  pcnt_unit_get_count(kPcntRight, &cnt);
  return cnt;
}

void EspIdfHal::setLed(uint8_t pattern) {
  // NeoPixel ring driven via RMT; simplified: patterns map to solid colors.
  // Full animation handled in led_task if needed — see main.cpp.
  (void)pattern;
}

} // namespace rover
