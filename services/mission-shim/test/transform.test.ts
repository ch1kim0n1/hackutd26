// Unit tests for module commandJson -> signed rover mission transform.
// Run: npx tsx test/transform.test.ts  (no broker needed)

import { createHmac } from 'node:crypto';
import { canonicalJson, signMission, transformCommand } from '../src/transform.js';

let passed = 0, failed = 0;
function check(name: string, cond: boolean, extra = '') {
  if (cond) { passed++; console.log(`  PASS ${name}`); }
  else { failed++; console.log(`  FAIL ${name} ${extra}`); }
}

const SECRET = 'test-shared-secret';
const CFG = { camera_id: 'cam-mast', routes: { 'wp-rack-a': 'patrol-rack', '*': 'patrol-main' } };
const FUTURE = new Date(Date.now() + 600_000).toISOString();

function cmd(over: Record<string, unknown> = {}) {
  return {
    schema_version: 1,
    command_id: 'mis-1',
    mission_id: 'mis-1',
    device_id: 'rover-01',
    type: 'inspect_zone',
    zone_id: 'rack-01',
    waypoint_id: 'wp-rack-a',
    expires_at: FUTURE,
    max_speed_mps: 0.2,
    ...over,
  };
}

// --- canonical json must match Python json.dumps(sort_keys, separators) ---
{
  const py = '{"a":1,"b":[true,null,"x"],"c":{"d":"e f"}}';
  check('canonical matches python form', canonicalJson({ a: 1, b: [true, null, 'x'], c: { d: 'e f' } }) === py);
}

// --- type mapping ---
{
  const r = transformCommand(cmd(), 'rover-01', CFG, SECRET);
  check('inspect_zone maps', r.ok && r.mission.type === 'inspect_zone' && r.mission.waypoint_id === 'wp-rack-a');
  check('inspect_zone keeps zone', r.ok && r.mission.zone_id === 'rack-01');
  check('signature present hex', r.ok && typeof r.mission.signature === 'string' && /^[0-9a-f]{64}$/.test(r.mission.signature));
}
{
  const r = transformCommand(cmd({ type: 'patrol' }), 'rover-01', CFG, SECRET);
  check('patrol -> patrol_route via waypoint map', r.ok && r.mission.type === 'patrol_route' && r.mission.route_id === 'patrol-rack');
}
{
  const r = transformCommand(cmd({ type: 'patrol', waypoint_id: 'wp-unknown' }), 'rover-01', CFG, SECRET);
  check('patrol falls back to wildcard route', r.ok && r.mission.route_id === 'patrol-main');
}
{
  const r = transformCommand(cmd({ type: 'patrol', waypoint_id: 'x' }), 'rover-01', { routes: {} }, SECRET);
  check('patrol without route mapping rejected', !r.ok);
}
{
  const r = transformCommand(cmd({ type: 'capture_photo', waypoint_id: '' }), 'rover-01', CFG, SECRET);
  check('capture_photo gets camera_id', r.ok && r.mission.camera_id === 'cam-mast' && r.mission.type === 'capture_photo');
}
{
  const r = transformCommand(cmd({ type: 'return_home', waypoint_id: '', zone_id: '' }), 'rover-01', CFG, SECRET);
  check('return_home maps clean', r.ok && r.mission.type === 'return_home');
}
{
  const r = transformCommand(cmd({ type: 'hold', waypoint_id: '', zone_id: '' }), 'rover-01', CFG, SECRET);
  check('hold -> stop', r.ok && r.mission.type === 'stop');
}
{
  const r = transformCommand(cmd({ type: 'launch_missiles' }), 'rover-01', CFG, SECRET);
  check('unknown type rejected', !r.ok);
}

// --- incident_id passthrough (inspection evidence linkage) ---
{
  const r = transformCommand(cmd({ incident_id: 'inc-42' }), 'rover-01', CFG, SECRET);
  check('incident_id passthrough', r.ok && r.mission.incident_id === 'inc-42');
  if (r.ok) {
    const { signature, ...unsigned } = r.mission;
    const expected = createHmac('sha256', SECRET)
      .update(canonicalJson(unsigned)).digest('hex');
    check('incident_id covered by signature', signature === expected);
  }
}
{
  const r = transformCommand(cmd({ incident_id: 'inc-💥' }), 'rover-01', CFG, SECRET);
  check('non-ascii incident_id rejected', !r.ok);
}
{
  const r = transformCommand(cmd(), 'rover-01', CFG, SECRET);
  check('absent incident_id stays absent', r.ok && !('incident_id' in r.mission));
}

// --- security checks ---
{
  const r = transformCommand(cmd({ device_id: 'rover-02' }), 'rover-01', CFG, SECRET);
  check('foreign device_id rejected', !r.ok);
}
{
  const r = transformCommand(cmd({ expires_at: '2020-01-01T00:00:00Z' }), 'rover-01', CFG, SECRET);
  check('still transforms (expiry is rover-side check)', r.ok);
}
{
  const r = transformCommand(cmd({ expires_at: 'not-a-date' }), 'rover-01', CFG, SECRET);
  check('bad expires_at rejected', !r.ok);
}
{
  const r = transformCommand(cmd({ waypoint_id: 'wp-rës' }), 'rover-01', CFG, SECRET);
  check('non-ascii rejected (signature safety)', !r.ok);
}
{
  const r = transformCommand('garbage', 'rover-01', CFG, SECRET);
  check('non-object rejected', !r.ok);
}

// --- signature must verify the same way rover auth.py does ---
{
  const r = transformCommand(cmd(), 'rover-01', CFG, SECRET);
  if (r.ok) {
    const { signature, ...unsigned } = r.mission;
    const expected = createHmac('sha256', SECRET)
      .update(canonicalJson(unsigned)).digest('hex');
    check('signature verifies over unsigned canonical', signature === expected);
    // wrong secret must NOT verify
    const wrong = createHmac('sha256', 'other').update(canonicalJson(unsigned)).digest('hex');
    check('wrong secret differs', signature !== wrong);
  } else {
    check('signature verifies over unsigned canonical', false, 'transform failed');
  }
}
{
  // signMission ignores a signature key if caller includes one (matches python)
  const m = { a: 1, signature: 'old' };
  const s1 = signMission(m, SECRET);
  const { signature: _s, ...rest } = m;
  check('signMission excludes signature field', s1 === createHmac('sha256', SECRET).update(canonicalJson(rest)).digest('hex'));
}

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);
