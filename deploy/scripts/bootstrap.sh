#!/usr/bin/env bash
# SENTINEL HIVE fresh-engineer bootstrap (issue #36).
#
# Brings up the reproducible dev/test deployment:
#   1. docker compose infra: mosquitto + spacetimedb + lab-executor
#   2. publish spacetimedb module (fresh -> --delete-data=always)
#   3. seed lab identities + registry (deploy/seeds)
#   4. generate gateway bindings
#   5. health-check everything; print next steps
#
# Idempotent: safe to re-run. Secrets live in deploy/env + deploy/secrets
# (both gitignored) — nothing sensitive is committed.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(cd .. && pwd)"

echo "== [0/5] secrets (generated locally, gitignored) =="
mkdir -p env secrets mosquitto
if [ ! -f env/mqtt.env ]; then
  cp env/mqtt.env.example env/mqtt.env
  # auto-generate dev passwords so the stack works out of the box;
  # replace with real lab credentials for anything beyond local dev
  for v in SENTINEL_GATEWAY_PASSWORD DEVICE_PUCK_A_01_PASSWORD DEVICE_ROVER_01_PASSWORD \
           DEVICE_PUCK_WIFI_01_PASSWORD DEVICE_KISMET_01_PASSWORD DEVICE_SDR_01_PASSWORD; do
    pw="$(openssl rand -hex 16)"
    sed -i '' "s|^${v}=.*|${v}=${pw}|" env/mqtt.env 2>/dev/null \
      || sed -i "s|^${v}=.*|${v}=${pw}|" env/mqtt.env
  done
  echo "generated deploy/env/mqtt.env with random dev passwords"
fi
./scripts/make-mosquitto-passwords.sh

echo "== [1/5] docker compose infra =="
docker compose -f docker-compose.yml up -d

echo "== [2/5] publish module =="
# fresh lab -> wipe and republish so bootstrapAdmin genesis works
( cd "$ROOT" && spacetime publish sentinel-hive --server http://127.0.0.1:3000 \
    --module-path spacetimedb --delete-data=always --yes )

echo "== [3/5] seed identities + registry =="
( cd seeds && npm install --silent && npm run generate --silent && npx tsx seed.ts )

echo "== [4/5] gateway bindings =="
( cd "$ROOT/services/gateway" && npm install --silent && npm run generate --silent )

if [ ! -f env/gateway.env ]; then
  cp env/gateway.env.example env/gateway.env
  echo "created env/gateway.env — fill SPACETIMEDB_TOKEN / EXECUTOR_SPACETIMEDB_TOKEN"
  echo "             and MQTT_PASSWORD from deploy/secrets/identities.json + mqtt.env"
fi
if [ ! -f mosquitto/passwordfile ]; then
  echo "NOTE: run deploy/scripts/make-mosquitto-passwords.sh after filling env/mqtt.env"
  echo "      then: docker compose -f deploy/docker-compose.yml restart mosquitto"
fi

echo "== [5/5] health checks =="
sleep 3
for svc in mosquitto spacetimedb lab-executor; do
  st="$(docker inspect -f '{{.State.Health.Status}}' "sh-$svc" 2>/dev/null || echo missing)"
  echo "  $svc: $st"
done

echo
echo "Bootstrap complete. Next:"
echo "  1. fill deploy/env/gateway.env + deploy/env/mqtt.env (no real secrets committed)"
echo "  2. deploy/scripts/make-mosquitto-passwords.sh && restart mosquitto"
echo "  3. cd services/gateway && set -a; . ../../deploy/env/gateway.env; set +a; npm start"
echo "  4. curl localhost:8081/healthz"
