import json
import sys
from datetime import datetime, timezone
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from publisher import canonical, envelope, parse_observation, reserve_seq


def observation():
    return {'device_id':'pi-01', 'hostname':'blindspot-pi1', 'observed_at':'2026-11-08T15:00:00+00:00', 'load_1m':0.25, 'memory_kib':{'MemTotal':1000,'MemAvailable':750}, 'disk_used_bytes':20, 'disk_total_bytes':200, 'tcp_listeners':['0.0.0.0:22','10.192.59.175:18080']}


def test_actual_observation_produces_measured_metrics_and_inventory():
    ts, metrics, inv = parse_observation(json.dumps(observation()), 'pi-01', {22, 18080}, datetime(2026,11,8,15,0,5,tzinfo=timezone.utc))
    assert metrics['load_1m_milli'] == 250 and metrics['provenance'] == 'LIVE'
    assert inv['unexpected'] == [] and ts == observation()['observed_at']
    obs = observation(); obs['tcp_listeners'].append('0.0.0.0:18082')
    _, _, inv = parse_observation(json.dumps(obs), 'pi-01', {22, 18080}, datetime(2026,11,8,15,0,5,tzinfo=timezone.utc))
    assert inv['unexpected'] == [18082]


def test_stale_wrong_identity_and_float_payload_are_rejected():
    with pytest.raises(ValueError): parse_observation(json.dumps(observation()), 'pi-02', {22}, datetime(2026,11,8,15,0,5,tzinfo=timezone.utc))
    with pytest.raises(ValueError): parse_observation(json.dumps(observation()), 'pi-01', {22}, datetime(2026,11,8,15,1,tzinfo=timezone.utc))
    with pytest.raises(ValueError): canonical({'value':1.0})


def test_sequence_is_durable_and_never_reused(tmp_path):
    path = tmp_path / 'sequence'
    assert reserve_seq(path, 20) == 21
    assert reserve_seq(path, 20) == 22
    with pytest.raises(ValueError): reserve_seq(path, 23)


def test_signed_payload_is_verified_by_existing_gateway():
    import subprocess
    root = Path(__file__).resolve().parents[3]
    obs = envelope('pi-01','rack-01',3,'2026-11-08T15:00:00Z','resource_metric',{'load_1m_milli':250},'x'*32)
    code = "import {verifyDeviceSignature,normalizeTelemetry} from './src/validate.ts'; const p=JSON.parse(process.argv[1]); if(!verifyDeviceSignature(p,'x'.repeat(32)) || !normalizeTelemetry(JSON.stringify(p),'pi-01',{'pi-01':'x'.repeat(32)}).ok) process.exit(1)"
    subprocess.run([str(root/'services/gateway/node_modules/.bin/tsx'), '-e', code, json.dumps(obs)], cwd=root/'services/gateway', check=True)
