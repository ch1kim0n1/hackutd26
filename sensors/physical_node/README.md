# Physical-node telemetry publisher

Publishes actual measurements from the hardware team's existing `blindspot-observe.service` journal. It does not replace the collector, control a device, or fabricate events. It signs `resource_metric` and `service_inventory` envelopes with the gateway's canonical HMAC contract and publishes QoS 1 to the device's own topic over TLS with certificate verification.

The unit is a **systemd user service** and requires the user to have permission to read the observation journal. A user manager may stop at logout or reboot unless the operator configures persistent user services. Provision the unique per-device broker identity, HMAC key and CA via an authenticated channel into an owner-only environment file; never commit them. `BLINDSPOT_SEQ_FLOOR` must be set from the gateway's recorded last sequence for that physical device before the first start. A persisted sequence must be retained across restarts; corrupt or out-of-date state fails closed.

Set the baseline `BLINDSPOT_ALLOWED_PORTS` from observed, authorized services (currently 22 and 18080 on each Pi); the publisher reports other actually observed ports in `unexpected`. A broker acknowledgement only confirms broker delivery, not gateway acceptance or database persistence. Those must be verified separately. No physical endpoint, listener or scenario is started by this service.

Required environment variable names: `BLINDSPOT_DEVICE_ID`, `BLINDSPOT_ZONE_ID`, `BLINDSPOT_MQTT_HOST`, `BLINDSPOT_MQTT_PORT`, `BLINDSPOT_MQTT_CA`, `BLINDSPOT_MQTT_USERNAME`, `BLINDSPOT_MQTT_PASSWORD`, `BLINDSPOT_HMAC_KEY`, `BLINDSPOT_SEQ_FLOOR`, `BLINDSPOT_ALLOWED_PORTS`, and `BLINDSPOT_STATE_DIR`. Requires Python 3 and `paho-mqtt==2.1.0` in an isolated virtual environment.
