# mission-shim

Device-side bridge: SpacetimeDB mission downlink → signed rover mission
file. Closes the gap between the module's unsigned `commandJson` and the
rover's HMAC-verified mission contract (PR #11).

## Flow

```
assignMission (module)
  -> gateway publishes commandJson to sentinel/v1/<device>/command
  -> mission-shim (MQTT, device credentials)
       transform + HMAC-SHA256 sign
  -> <inbox>/<device>/<mission_id>.json   (atomic rename, idempotent)
  -> rover-mission watch-missions <inbox>/<device>
       validates signature + contract, executes, writes .done
  -> rover telemetry (MQTT) -> gateway -> ingestObservation(mission_status)
```

## Type mapping (module -> rover)

| module `type`   | rover `type`    | extra fields                          |
|-----------------|-----------------|---------------------------------------|
| `inspect_zone`  | `inspect_zone`  | `zone_id`, `waypoint_id` passthrough  |
| `patrol`        | `patrol_route`  | `route_id` via `routes` map or `*`    |
| `capture_photo` | `capture_photo` | `camera_id` (default `cam-mast`)      |
| `return_home`   | `return_home`   | —                                     |
| `hold`          | `stop`          | —                                     |

Unmapped types and missing route/camera config are rejected, never
guessed. Non-ASCII fields are rejected — JS and Python canonical JSON
diverge there and the rover's signature check would fail.

## Config (env only)

```bash
MQTT_URL=mqtt://device-rover-01:<pw>@127.0.0.1:1883
SHIM_SIGNING_SECRET=<same as rover's ROVER_MISSION_SECRET>
SHIM_INBOX_DIR=./mission-inbox
SHIM_DEVICES='{"rover-01":{"camera_id":"cam-mast",
  "routes":{"wp-rack-a":"patrol-rack","*":"patrol-main"},
  "mqtt_username":"device-rover-01","mqtt_password":"<pw>"}}'
# optional: SHIM_COMMAND_TOPIC (default sentinel/v1/{device}/command)
```

Per-device `secret_env` overrides `SHIM_SIGNING_SECRET` for multi-rover
deployments. Per-device `mqtt_username`/`mqtt_password` override the
broker account (ACL: a device reads only its own command topic).

## Test

```bash
npm install && npm test   # 19 transform/signature checks, no broker
```

Cross-language proof: a shim-produced mission passes
`rover-mission validate` and executes via `watch-missions` (verified
end-to-end: inspect_zone -> wp-rack-a -> evidence -> completed).
