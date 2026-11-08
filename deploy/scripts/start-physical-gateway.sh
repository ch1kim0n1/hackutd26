#!/usr/bin/env bash
# Start the configured physical-demo gateway without creating or resetting a DB.
set -euo pipefail
repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
config_file="$repo_root/deploy/env/physical-gateway.env"
if [[ ! -f "$config_file" ]]; then echo 'Physical gateway configuration is missing.' >&2; exit 1; fi
if ! curl -fsS --max-time 3 http://127.0.0.1:3000/v1/ping >/dev/null; then
  echo 'SpacetimeDB is unavailable; start the existing sh-spacetimedb container first.' >&2; exit 1
fi
if [[ "$(docker inspect -f '{{.State.Running}}' blindspot-physical-mqtt 2>/dev/null || true)" != 'true' ]]; then
  echo 'Starting the dedicated physical-demo MQTT broker.'
  docker start blindspot-physical-mqtt >/dev/null
fi
set -a
# Local file is owner-only and contains secrets; never print it.
. "$config_file"
set +a
cd "$repo_root/services/gateway"
exec npm start
