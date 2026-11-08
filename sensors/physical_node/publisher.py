"""Publish the existing physical-node journal measurements as signed MQTT.

Runs alongside blindspot-observe; never changes the collector or issues
commands to the Pis. Broker PUBACK is not evidence of gateway acceptance.
"""
from __future__ import annotations

import fcntl
import hashlib
import hmac
import json
import math
import os
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path


def canonical(value):
    # Integers/ASCII only: no Python/JS float or Unicode canonical mismatch.
    def validate(v):
        if isinstance(v, str):
            if not v.isascii():
                raise ValueError('non-ASCII data')
        elif isinstance(v, bool) or v is None or isinstance(v, int):
            pass
        elif isinstance(v, list):
            for x in v: validate(x)
        elif isinstance(v, dict):
            for k, x in v.items():
                if not isinstance(k, str) or not k.isascii(): raise ValueError('invalid key')
                validate(x)
        else:
            raise ValueError('unsupported value in signed payload')
    validate(value)
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


def parse_observation(raw, device_id, allowed_ports, now=None):
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get('device_id') != device_id:
        raise ValueError('wrong device identity')
    ts = data.get('observed_at')
    if not isinstance(ts, str): raise ValueError('missing observation time')
    at = datetime.fromisoformat(ts.replace('Z', '+00:00'))
    if at.tzinfo is None: raise ValueError('timestamp must have timezone')
    age = (now or datetime.now(timezone.utc)) - at.astimezone(timezone.utc)
    if age.total_seconds() < -5 or age.total_seconds() > 35:
        raise ValueError('observation is stale or clock is ahead')
    listeners = data.get('tcp_listeners')
    if not isinstance(listeners, list) or any(not isinstance(x, str) or not x.isascii() for x in listeners):
        raise ValueError('invalid listener inventory')
    ports = set()
    for entry in listeners:
        suffix = entry.rsplit(':', 1)[-1]
        if not suffix.isdigit() or not 1 <= int(suffix) <= 65535:
            raise ValueError('invalid listener port')
        ports.add(int(suffix))
    load = data.get('load_1m')
    memory = data.get('memory_kib')
    if not isinstance(load, (int, float)) or isinstance(load, bool) or not math.isfinite(load) or load < 0 or not isinstance(memory, dict):
        raise ValueError('invalid resource metrics')
    def nonnegative(v):
        if type(v) is not int or v < 0 or v > 2**53 - 1: raise ValueError('invalid measured integer')
        return v
    hostname = data.get('hostname')
    if not isinstance(hostname, str) or not hostname.isascii() or not hostname:
        raise ValueError('invalid hostname')
    metrics = {'provenance':'LIVE', 'hostname':hostname, 'load_1m_milli':round(load * 1000),
               'memory_total_kib':nonnegative(memory.get('MemTotal')), 'memory_available_kib':nonnegative(memory.get('MemAvailable')),
               'disk_used_bytes':nonnegative(data.get('disk_used_bytes')), 'disk_total_bytes':nonnegative(data.get('disk_total_bytes'))}
    inventory = {'provenance':'LIVE', 'listeners':sorted(listeners), 'unexpected':sorted(ports - allowed_ports)}
    return ts, metrics, inventory


def reserve_seq(path, floor):
    # Persist before publishing: a crash can skip a sequence but cannot reuse it.
    path = Path(path)
    if path.exists():
        last = int(path.read_text().strip())
        if last < floor: raise ValueError('saved sequence below configured floor')
    else:
        last = floor
    if last < 0 or last >= 2**53 - 1: raise ValueError('invalid sequence')
    value = last + 1
    temp = path.with_name(path.name + '.tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f:
        f.write(str(value) + '\n'); f.flush(); os.fsync(f.fileno())
    os.replace(temp, path)
    directory = os.open(path.parent, os.O_RDONLY)
    try: os.fsync(directory)
    finally: os.close(directory)
    return value


def envelope(device, zone, seq, timestamp, kind, data, key):
    body = {'schema_version':1, 'event_id':str(uuid.uuid4()), 'device_id':device,
            'seq':seq, 'observed_at':timestamp, 'kind':kind, 'zone_id':zone, 'data':data}
    body['signature'] = hmac.new(key.encode('ascii'), canonical(body).encode('ascii'), hashlib.sha256).hexdigest()
    return body


def main():
    import paho.mqtt.client as mqtt
    device = os.environ['BLINDSPOT_DEVICE_ID']
    zone = os.environ['BLINDSPOT_ZONE_ID']
    host = os.environ['BLINDSPOT_MQTT_HOST']
    user = os.environ['BLINDSPOT_MQTT_USERNAME']
    password = os.environ['BLINDSPOT_MQTT_PASSWORD']
    key = os.environ['BLINDSPOT_HMAC_KEY']
    ca_file = os.environ['BLINDSPOT_MQTT_CA']
    floor = int(os.environ['BLINDSPOT_SEQ_FLOOR'])
    allowed = {int(p) for p in os.environ['BLINDSPOT_ALLOWED_PORTS'].split(',')}
    if device not in ('pi-01', 'pi-02') or not zone.isascii() or not key.isascii() or len(key) < 32 or not password or not user or not Path(ca_file).is_file() or not allowed or any(p < 1 or p > 65535 for p in allowed):
        raise SystemExit('invalid or missing publisher configuration')
    state_dir = Path(os.environ['BLINDSPOT_STATE_DIR'])
    state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (state_dir / 'publisher.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='blindspot-' + device)
        client.tls_set(ca_certs=ca_file)
        client.username_pw_set(user, password)
        client.connect(host, int(os.environ.get('BLINDSPOT_MQTT_PORT', '8884')), keepalive=30)
        client.loop_start()
        try:
            while True:
                try:
                    journal = subprocess.run(['journalctl','-u','blindspot-observe.service','-n','1','--no-pager','-o','cat'], capture_output=True, text=True, timeout=5, check=True)
                    timestamp, metrics, inventory = parse_observation(journal.stdout.strip(), device, allowed)
                    for kind, data in [('resource_metric', metrics), ('service_inventory', inventory)]:
                        seq = reserve_seq(state_dir / 'sequence', floor)
                        msg = envelope(device, zone, seq, timestamp, kind, data, key)
                        result = client.publish(f'sentinel/v1/{device}/telemetry', canonical(msg), qos=1)
                        result.wait_for_publish(timeout=10)
                        if not result.is_published(): raise RuntimeError('MQTT publish not acknowledged')
                        print(f'broker_ack device={device} kind={kind} seq={seq} event_id={msg["event_id"]}', flush=True)
                except (ValueError, OSError, subprocess.SubprocessError, RuntimeError) as exc:
                    print(f'publisher_error type={type(exc).__name__}', flush=True)
                time.sleep(10)
        finally:
            client.loop_stop(); client.disconnect()


if __name__ == '__main__':
    main()
