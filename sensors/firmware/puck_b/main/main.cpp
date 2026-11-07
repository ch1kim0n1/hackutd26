/* Puck B — ESP32 cabinet reed-switch observer.
 * Debounced open/close -> cabinet_contact_* events (docs/04).
 * `authorized` is set only inside a provisioned maintenance window —
 * mirrors sensors/pucks/src/puck_core/puck_b.py. H08 pending. */
#include <cstdio>
#include <cstring>
#include <string>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "nvs_flash.h"
#include "puck_sign.h"

static const char *TAG = "puck-b";
static const char *DEVICE_ID = "puck-b-01";
static const char *ZONE_ID = "cabinet-01";
static const gpio_num_t REED_GPIO = GPIO_NUM_4;   /* NO reed: open=1 */
static const gpio_num_t LED_GPIO = GPIO_NUM_2;
static const int SAMPLE_MS = 10;
static const int DEBOUNCE_MS = 50;

static uint8_t g_secret[32];
static int g_seq = 0;
static bool g_stable_closed = true;
static bool g_pending_closed = true;
static int64_t g_pending_since_ms = 0;
static bool g_init = false;

/* Maintenance window: provisioned via NVS as [start_epoch,end_epoch).
   0/0 = none -> every open is authorized=false (PHY01 input). */
static int64_t g_win_start = 0, g_win_end = 0;

static void load_config(void) {
    memset(g_secret, 0, sizeof(g_secret));
    /* TODO(hardware): NVS keys "secret", "win_start", "win_end" */
}

static bool in_maintenance_window(int64_t now_ms) {
    if (!g_win_start && !g_win_end) return false;
    return now_ms >= g_win_start && now_ms < g_win_end;
}

static void emit_event(bool closed, bool in_window) {
    int64_t now_ms = esp_timer_get_time() / 1000;
    const char *kind = closed ? "cabinet_contact_closed" : "cabinet_contact_open";
    char line[512];
    int n = snprintf(line, sizeof(line),
        "{\"schema_version\":1,\"event_id\":\"evt-%lld\",\"device_id\":\"%s\","
        "\"seq\":%d,\"observed_at\":\"%lld\",\"kind\":\"%s\",\"zone_id\":\"%s\","
        "\"data\":{\"contact\":\"%s\",\"authorized\":%s,"
        "\"maintenance_window\":%s}}",
        (long long)now_ms, DEVICE_ID, ++g_seq, (long long)now_ms, kind, ZONE_ID,
        closed ? "closed" : "open",
        (!closed && in_window) || closed ? "true" : "false",
        in_window ? "true" : "false");
    printf("%s\n", line);   /* serial -> collector */
    ESP_LOGI(TAG, "%s authorized=%d", kind, !closed && in_window);
}

extern "C" void app_main(void) {
    nvs_flash_init();
    load_config();
    gpio_config_t io = {};
    io.pin_bit_mask = 1ULL << REED_GPIO;
    io.mode = GPIO_MODE_INPUT;
    io.pull_up_en = GPIO_PULLUP_ENABLE;   /* NO contact -> reads LOW when open */
    gpio_config(&io);
    gpio_config_t led = {};
    led.pin_bit_mask = 1ULL << LED_GPIO;
    led.mode = GPIO_MODE_OUTPUT;
    gpio_config(&led);

    bool last_raw = gpio_get_level(REED_GPIO) == 0; /* closed = magnet near */
    g_init = true;
    g_stable_closed = g_pending_closed = last_raw;
    ESP_LOGI(TAG, "puck-b %s zone=%s debounce=%dms — H08 pending",
             DEVICE_ID, ZONE_ID, DEBOUNCE_MS);
    for (;;) {
        bool raw_closed = gpio_get_level(REED_GPIO) == 0;
        int64_t now = esp_timer_get_time() / 1000;
        if (raw_closed == g_pending_closed) {
            if (raw_closed != g_stable_closed &&
                now - g_pending_since_ms >= DEBOUNCE_MS) {
                g_stable_closed = raw_closed;
                emit_event(g_stable_closed, in_maintenance_window(now));
                gpio_set_level(LED_GPIO, g_stable_closed ? 0 : 1);
            }
        } else {
            g_pending_closed = raw_closed;
            g_pending_since_ms = now;
        }
        vTaskDelay(pdMS_TO_TICKS(SAMPLE_MS));
    }
}
