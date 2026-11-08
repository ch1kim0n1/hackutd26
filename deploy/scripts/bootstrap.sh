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
fi
# Fill any empty PASSWORD var with a random dev password so the stack works
# out of the box; values already set are never overwritten. Replace with
# real lab credentials for anything beyond local dev.
for v in SENTINEL_GATEWAY_PASSWORD DEVICE_PUCK_A_01_PASSWORD DEVICE_ROVER_01_PASSWORD \
         DEVICE_PUCK_WIFI_01_PASSWORD DEVICE_KISMET_01_PASSWORD DEVICE_SDR_01_PASSWORD; do
  if grep -qE "^${v}=(\"\"|'')?$" env/mqtt.env; then
    pw="$(openssl rand -hex 16)"
    sed -i '' "s|^${v}=.*|${v}=${pw}|" env/mqtt.env 2>/dev/null \
      || sed -i "s|^${v}=.*|${v}=${pw}|" env/mqtt.env
    echo "generated $v"
  fi
done
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
fi
# Fill still-empty gateway.env secrets from the generated identities +
# mqtt.env so the gateway runs with zero manual steps. Idempotent: any
# value already set by the operator is kept.
if [ -f secrets/identities.json ]; then
  GW_URI="$(grep '^SPACETIMEDB_URI=' env/gateway.env | cut -d= -f2- || true)"
  GW_URI="${GW_URI:-ws://127.0.0.1:3000}"
  GW_TOK="$(node -e 'const t=require("./secrets/identities.json");const u=process.argv[1];process.stdout.write(((t[u]||{}).gateway)||"")' "$GW_URI" 2>/dev/null || true)"
  EX_TOK="$(node -e 'const t=require("./secrets/identities.json");const u=process.argv[1];process.stdout.write(((t[u]||{}).executor)||"")' "$GW_URI" 2>/dev/null || true)"
  GW_MQTT_PW="$(grep '^SENTINEL_GATEWAY_PASSWORD=' env/mqtt.env | cut -d= -f2- || true)"
  fill_env() { # KEY VALUE — replace only an empty assignment
    local k="$1" v="$2"
    [ -n "$v" ] || return 0
    if grep -qE "^${k}=(\"\"|'')?$" env/gateway.env; then
      local esc="${v//&/\\&}"; esc="${esc//|/\\|}"
      sed -i '' "s|^${k}=.*|${k}=${esc}|" env/gateway.env 2>/dev/null \
        || sed -i "s|^${k}=.*|${k}=${esc}|" env/gateway.env
      echo "  filled $k"
    fi
  }
  fill_env SPACETIMEDB_TOKEN "$GW_TOK"
  fill_env EXECUTOR_SPACETIMEDB_TOKEN "$EX_TOK"
  fill_env MQTT_PASSWORD "$GW_MQTT_PW"
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
echo "Bootstrap complete. gateway.env secrets were auto-filled from"
echo "deploy/secrets/identities.json + env/mqtt.env (gitignored). Next:"
echo "  1. cd services/gateway && set -a; . ../../deploy/env/gateway.env; set +a; npm start"
echo "  2. curl localhost:8081/healthz"
echo "  3. tests: cd spacetimedb && npm run test:smoke   (needs a FRESH db —"
echo "     see deploy/README.md 'Tests / evidence')"
