/* Puck C — ESP32 BLE observer restricted to enrolled lab beacons.
 * Non-enrolled advertisements are dropped on-device (counted only) —
 * mirrors sensors/pucks/src/puck_core/puck_c.py. H08 pending. */
#include <cstdio>
#include <cstring>
#include <string>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_bt.h"
#include "esp_bt_main.h"
#include "esp_gap_ble_api.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "nvs_flash.h"
#include "puck_sign.h"

static const char *TAG = "puck-c";
static const char *DEVICE_ID = "puck-c-01";
static const char *ZONE_ID = "lab-bench";
static const int SCAN_WINDOW_MS = 5000;
static const int DEDUP_WINDOW_MS = 10000;

static uint8_t g_secret[32];
static int g_seq = 0;
static int g_dropped = 0;

/* Enrolled beacon keys provisioned in NVS (bt address or service UUID).
   Conservative default: empty -> all BLE dropped. */
static char g_enrolled[8][37];
static int g_enrolled_n = 0;

struct Seen { char key[37]; int64_t ms; };
static Seen g_seen[16];
static int g_seen_n = 0;

static void load_config(void) {
    memset(g_secret, 0, sizeof(g_secret));
    memset(g_enrolled, 0, sizeof(g_enrolled));
    /* TODO(hardware): NVS "enrolled" blob + "secret" key */
}

static bool is_enrolled(const uint8_t *addr, esp_ble_addr_type_t type,
                        const esp_ble_gap_adv_data_t *adv) {
    char key[37];
    snprintf(key, sizeof(key), "%02x:%02x:%02x:%02x:%02x:%02x",
             addr[0], addr[1], addr[2], addr[3], addr[4], addr[5]);
    for (int i = 0; i < g_enrolled_n; i++) {
        if (!strcasecmp(g_enrolled[i], key)) return true;
        /* service-UUID enrollment checked against adv->uuid16_list etc.
           TODO(hardware): parse complete/local 128-bit UUID lists */
    }
    return false;
}

static void emit_beacon(const uint8_t *addr, int8_t rssi) {
    int64_t now_ms = esp_timer_get_time() / 1000;
    char key[37];
    snprintf(key, sizeof(key), "%02x:%02x:%02x:%02x:%02x:%02x",
             addr[0], addr[1], addr[2], addr[3], addr[4], addr[5]);
    for (int i = 0; i < g_seen_n; i++) {
        if (!strcmp(g_seen[i].key, key) &&
            now_ms - g_seen[i].ms < DEDUP_WINDOW_MS) return;
    }
    if (g_seen_n < 16) {
        strncpy(g_seen[g_seen_n].key, key, 36);
        g_seen[g_seen_n].ms = now_ms;
        g_seen_n++;
    }
    char line[512];
    int n = snprintf(line, sizeof(line),
        "{\"schema_version\":1,\"event_id\":\"evt-%lld\",\"device_id\":\"%s\","
        "\"seq\":%d,\"observed_at\":\"%lld\",\"kind\":\"ble_beacon_seen\","
        "\"zone_id\":\"%s\",\"data\":{\"beacon_key\":\"%s\",\"address\":\"%s\","
        "\"rssi_dbm\":%d,\"enrolled\":true}}",
        (long long)now_ms, DEVICE_ID, ++g_seq, (long long)now_ms, ZONE_ID,
        key, key, rssi);
    printf("%s\n", line);
    ESP_LOGI(TAG, "enrolled beacon %s rssi=%d", key, rssi);
}

static void gap_cb(esp_gap_ble_cb_event_t event, esp_ble_gap_cb_param_t *param) {
    if (event == ESP_GAP_BLE_SCAN_RESULT_EVT &&
        param->scan_rst.search_evt_type == ESP_GAP_SEARCH_INQ_RES_EVT) {
        const auto &r = param->scan_rst;
        if (!is_enrolled(r.bda, r.ble_addr_type, nullptr)) {
            g_dropped++;   /* counted only — no identifiers retained */
            return;
        }
        emit_beacon(r.bda, r.rssi);
    }
}

extern "C" void app_main(void) {
    nvs_flash_init();
    load_config();
    ESP_ERROR_CHECK(esp_bt_controller_mem_release(ESP_BT_MODE_CLASSIC_BT));
    ESP_ERROR_CHECK(esp_bt_controller_enable(ESP_BT_MODE_BLE));
    ESP_ERROR_CHECK(esp_bluedroid_init());
    ESP_ERROR_CHECK(esp_bluedroid_enable());
    ESP_ERROR_CHECK(esp_ble_gap_register_callback(gap_cb));
    esp_ble_gap_set_device_name("puck-c-01");
    esp_ble_gap_config_adv_data(NULL);
    /* passive-ish scan: actively scan for enrolled beacons only */
    esp_ble_gap_set_scan_params(&(esp_ble_scan_params_t){
        .scan_type = BLE_SCAN_TYPE_ACTIVE,
        .own_addr_type = BLE_ADDR_TYPE_PUBLIC,
        .scan_filter_policy = BLE_SCAN_FILTER_ALLOW_ALL,
        .scan_interval = 0x50,
        .scan_window = 0x30,
        .scan_duplicate = BLE_SCAN_DUPLICATE_DISABLE,
    });
    ESP_LOGI(TAG, "puck-c %s zone=%s enrolled=%d dropped=%d — H08 pending",
             DEVICE_ID, ZONE_ID, g_enrolled_n, g_dropped);
    for (;;) {
        esp_ble_gap_start_scanning(SCAN_WINDOW_MS);
        vTaskDelay(pdMS_TO_TICKS(SCAN_WINDOW_MS + 500));
    }
}
