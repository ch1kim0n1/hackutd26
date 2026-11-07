/* Puck A — ESP32-S3 2.4 GHz Wi-Fi observation puck.
 * Emits canonical wifi_ap_seen events (docs/04) over serial/MQTT.
 * Logic mirrors sensors/pucks/src/puck_core/puck_a.py — keep in sync.
 * NOT yet validated on hardware (bring-up gate H08). */
#include <cstdio>
#include <cstring>
#include <string>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_log.h"
#include "nvs_flash.h"
#include "puck_sign.h"

static const char *TAG = "puck-a";
static const char *DEVICE_ID = "puck-a-01";   /* provisioned per unit */
static const char *ZONE_ID = "rack-01";
static const int SCAN_INTERVAL_MS = 5000;
static const int DEDUP_WINDOW_MS = 5000;

/* Provisioned at flash time: HMAC key + known-BSSID inventory in NVS.
   Placeholder here — real build reads nvs; never hardcode secrets. */
static uint8_t g_secret[32];

struct SeenAp { char bssid[18]; char ssid[33]; uint8_t channel; int8_t rssi; int64_t ms; };
static SeenAp g_seen[32];
static int g_seen_n = 0;

static void load_secret(void) {
    /* TODO(hardware): read 32-byte HMAC key from NVS partition
       "puck" namespace key "secret". For bench bring-up a dev key is
       injected via esptool/nvs; this build ships no key material. */
    memset(g_secret, 0, sizeof(g_secret));
}

static bool is_known_bssid(const char *ssid, const char *bssid) {
    /* TODO(hardware): compare against NVS-stored authorized inventory.
       Conservative default: nothing known -> every AP flagged
       ssid_known=false rather than silently trusted. */
    (void)ssid; (void)bssid;
    return false;
}

static int g_seq = 0;

static void emit_ap(const wifi_ap_record_t &ap) {
    char bssid[18];
    snprintf(bssid, sizeof(bssid), "%02x:%02x:%02x:%02x:%02x:%02x",
             ap.bssid[0], ap.bssid[1], ap.bssid[2],
             ap.bssid[3], ap.bssid[4], ap.bssid[5]);
    int64_t now_ms = esp_timer_get_time() / 1000;
    /* dedup: same bssid within DEDUP_WINDOW_MS -> skip (mirrors puck_a.py) */
    for (int i = 0; i < g_seen_n; i++) {
        if (!strcmp(g_seen[i].bssid, bssid) &&
            now_ms - g_seen[i].ms < DEDUP_WINDOW_MS) {
            return;
        }
    }
    if (g_seen_n < 32) {
        strncpy(g_seen[g_seen_n].bssid, bssid, 17);
        g_seen[g_seen_n].ms = now_ms;
        g_seen_n++;
    }
    bool known = is_known_bssid((const char *)ap.ssid, bssid);
    char line[512];
    int n = snprintf(line, sizeof(line),
        "{\"schema_version\":1,\"event_id\":\"evt-%lld\",\"device_id\":\"%s\","
        "\"seq\":%d,\"observed_at\":\"%lld\",\"kind\":\"wifi_ap_seen\","
        "\"zone_id\":\"%s\",\"data\":{\"ssid\":\"%s\",\"bssid\":\"%s\","
        "\"channel\":%d,\"rssi_dbm\":%d,\"source_id\":\"%s\","
        "\"known_bssid\":%s,\"ssid_known\":%s}}",
        (long long)now_ms, DEVICE_ID, ++g_seq, (long long)now_ms, ZONE_ID,
        (char *)ap.ssid, bssid, ap.primary, ap.rssi, DEVICE_ID,
        known ? "true" : "false", known ? "true" : "false");
    uint8_t mac[32];
    puck_sign_hmac(g_secret, sizeof(g_secret), (uint8_t *)line, n, mac);
    printf("%s\n", line);  /* serial transport -> collector gateway */
    ESP_LOGI(TAG, "ap %s ch%d rssi%d known=%d", bssid, ap.primary, ap.rssi, known);
}

static void wifi_event_handler(void *arg, esp_event_base_t base,
                               int32_t id, void *data) {
    if (base == WIFI_EVENT && id == WIFI_EVENT_SCAN_DONE) {
        uint16_t n = 0;
        esp_wifi_scan_get_ap_num(&n);
        wifi_ap_record_t *recs = malloc(n * sizeof(wifi_ap_record_t));
        esp_wifi_scan_get_ap_records(&n, recs);
        for (int i = 0; i < (int)n; i++) emit_ap(recs[i]);
        free(recs);
    }
}

extern "C" void app_main(void) {
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        nvs_flash_erase(); nvs_flash_init();
    }
    load_secret();
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        WIFI_EVENT, ESP_EVENT_ANY_ID, &wifi_event_handler, NULL, NULL));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_LOGI(TAG, "puck-a %s zone=%s scan=%dms — H08 hardware validation pending",
             DEVICE_ID, ZONE_ID, SCAN_INTERVAL_MS);
    for (;;) {
        esp_wifi_scan_start(NULL, false);
        vTaskDelay(pdMS_TO_TICKS(SCAN_INTERVAL_MS));
    }
}
