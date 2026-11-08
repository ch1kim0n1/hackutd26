#!/usr/bin/env bash
# Generate deploy/mosquitto/passwordfile from deploy/env/mqtt.env.
# Uses local mosquitto_passwd when present, else runs it inside the
# eclipse-mosquitto image (no local install needed).
set -euo pipefail
cd "$(dirname "$0")/.."

ENV_FILE="${1:-env/mqtt.env}"
[ -f "$ENV_FILE" ] || { echo "missing $ENV_FILE — copy env/mqtt.env.example first"; exit 1; }

set -a; . "$ENV_FILE"; set +a
OUT="mosquitto/passwordfile"
: > "$OUT"
chmod 0600 "$OUT" 2>/dev/null || true

USE_DOCKER=0
if command -v mosquitto_passwd >/dev/null; then
  USE_DOCKER=0
elif docker image inspect eclipse-mosquitto:2.0.20 >/dev/null 2>&1; then
  USE_DOCKER=1
else
  echo "need mosquitto_passwd or the eclipse-mosquitto:2.0.20 image"; exit 1
fi

add() { # user envvar
  local user="$1" var="$2" pw="${!2:-}"
  [ -n "$pw" ] || { echo "skip $user (no password in $ENV_FILE)"; return; }
  if [ "$USE_DOCKER" = "1" ]; then
    docker run --rm -v "$PWD/mosquitto:/m" eclipse-mosquitto:2.0.20 \
      mosquitto_passwd -b /m/passwordfile "$user" "$pw" >/dev/null
  else
    mosquitto_passwd -b "$OUT" "$user" "$pw"
  fi
  echo "added $user"
}

add sentinel-gateway SENTINEL_GATEWAY_PASSWORD
add device-puck-a-01 DEVICE_PUCK_A_01_PASSWORD
add device-rover-01 DEVICE_ROVER_01_PASSWORD
add device-puck-wifi-01 DEVICE_PUCK_WIFI_01_PASSWORD
add device-kismet-01 DEVICE_KISMET_01_PASSWORD
add device-sdr-01 DEVICE_SDR_01_PASSWORD
add device-puck-b-01 DEVICE_PUCK_B_01_PASSWORD
add device-puck-c-01 DEVICE_PUCK_C_01_PASSWORD
add device-datacenter-sim DEVICE_DATACENTER_SIM_PASSWORD

echo "wrote $OUT (gitignored)"
