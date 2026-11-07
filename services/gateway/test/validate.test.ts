// Unit tests for telemetry envelope validation + rover normalization.
// Run: npx tsx test/validate.test.ts  (no broker/DB needed)

import { normalizeTelemetry, validateEnvelope } from '../src/validate.js';

const sleep = () => {};
void sleep;

let passed = 0, failed = 0;
function check(name: string, cond: boolean, extra = '') {
  if (cond) { passed++; console.log(`  PASS ${name}`); }
  else { failed++; console.log(`  FAIL ${name} ${extra}`); }
}

const now = new Date().toISOString();
const canonical = {
  schema_version: 1,
  event_id: 'e1',
  device_id: 'puck-a-01',
  seq: 7,
  observed_at: now,
  kind: 'contact_open',
  zone_id: 'rack-01',
  data: { switch: 'reed-1' },
};

const enc = (o: unknown) => Buffer.from(JSON.stringify(o), 'utf8');

// --- canonical path ---
{
  const r = validateEnvelope(enc(canonical), 'puck-a-01');
  check('canonical valid', r.ok && r.value.seq === 7n && r.value.kind === 'contact_open');
}
{
  const r = validateEnvelope(enc({ ...canonical, device_id: 'other' }), 'puck-a-01');
  check('canonical device mismatch rejected', !r.ok);
}
{
  const r = validateEnvelope(enc({ ...canonical, seq: -1 }), 'puck-a-01');
  check('negative seq rejected', !r.ok);
}

// --- rover normalization ---
const roverEvent = {
  event: 'navigating',
  schema_version: 1,
  device_id: 'rover-01',
  mission_id: 'mis-abc',
  command_id: 'cmd-mis-abc',
  type: 'inspect_zone',
  state: 'navigating',
  zone_id: 'rack-01',
  pose_confidence: 0.9,
  reason: '',
  observed_at: now,
  pose: { x: 1.2, y: 3.4, heading_rad: 0.5, confidence: 0.9, source: 'test' },
};

{
  const r = normalizeTelemetry(enc(roverEvent), 'rover-01');
  check('rover event normalized', r.ok && r.value.kind === 'mission_status' && r.value.seqAssigned);
  if (r.ok) {
    const d = JSON.parse(r.value.dataJson);
    check('rover data carries mission fields', d.mission_id === 'mis-abc' && d.state === 'navigating' && !!d.pose);
    check('event_id deterministic', r.value.eventId.includes('mis-abc') && r.value.eventId.includes('navigating'));
  }
}
{
  // same event twice -> same event_id (dedupe upstream)
  const a = normalizeTelemetry(enc(roverEvent), 'rover-01');
  const b = normalizeTelemetry(enc(roverEvent), 'rover-01');
  check('rover event_id stable for dedupe', a.ok && b.ok && a.value.eventId === b.value.eventId);
}
{
  const r = normalizeTelemetry(enc({ ...roverEvent, device_id: 'puck-a-01' }), 'rover-01');
  check('rover device mismatch rejected', !r.ok);
}
{
  const r = normalizeTelemetry(enc({ ...roverEvent, zone_id: null }), 'rover-01');
  check('rover missing zone rejected', !r.ok);
}
{
  // puck kind (sensors/pucks) now admitted
  const r = validateEnvelope(enc({ ...canonical, device_id: 'puck-b-01', kind: 'cabinet_contact_open' }), 'puck-b-01');
  check('puck cabinet_contact_open admitted', r.ok && r.value.kind === 'cabinet_contact_open');
}
{
  // garbage still rejected with original reason
  const r = normalizeTelemetry(enc({ hello: 'world' }), 'rover-01');
  check('non-envelope rejected', !r.ok);
}
{
  // canonical still wins over rover path
  const r = normalizeTelemetry(enc(canonical), 'puck-a-01');
  check('canonical not seq-assigned', r.ok && !r.value.seqAssigned && r.value.seq === 7n);
}

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);
