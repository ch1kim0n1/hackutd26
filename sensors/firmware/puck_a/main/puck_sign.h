#pragma once
#include <stddef.h>
#include <stdint.h>
/* HMAC-SHA256 over the canonical event JSON. Secret lives in NVS/efuse,
   flashed per-device at provisioning — never committed (docs/08). */
bool puck_sign_hmac(const uint8_t *key, size_t key_len,
                    const uint8_t *msg, size_t msg_len,
                    uint8_t out[32]);
