// Fixture-driven tests for the sentinel.rover.* v1 common contract (issue #115).
// Consumes contracts/rover/fixtures/*.json — the same files the Python suites
// consume — so all three stacks prove identical behavior.
// Run: npx tsx test/common.test.ts

import { readFileSync } from 'node:fs';
import {
  autonomyReportToCommon, commandToCommon, commonToCommand,
  commonToModuleEvidenceRow, commonToRoverMission, evidenceToCommon,
  moduleReportFields, roverEventToCommon, roverToCommon,
  validateCommonEvidence, validateCommonMission, validateCommonTelemetry,
  STATE_TO_MODULE_DEVICE, type Provenance,
} from '../src/common.js';
import { canonicalJson, signMission } from '../src/transform.js';
import type { DeviceShimConfig } from '../src/config.js';

let passed = 0, failed = 0;
function check(name: string, cond: boolean, extra = '') {
  if (cond) { passed++; console.log(`  PASS ${name}`); }
  else { failed++; console.log(`  FAIL ${name} ${extra}`); }
}
function eq(name: string, a: unknown, b: unknown) {
  check(name, canonicalJson(a) === canonicalJson(b),
    `\n    got:  ${canonicalJson(a)}\n    want: ${canonicalJson(b)}`);
}

const SECRET = 'contract-test-secret';
const DEVICE = 'rover-01';
const FIX = (n: string) =>
  JSON.parse(readFileSync(new URL(`../../../contracts/rover/fixtures/${n}`, import.meta.url), 'utf8'));
const MISSIONS = FIX('missions.json');
const TELEMETRY = FIX('telemetry.json');
const EVIDENCE = FIX('evidence.json');
const stripSig = (m: Record<string, unknown>) => {
  const { signature: _s, ...rest } = m; return rest;
};
// commandJson transports neither issued_at (producer metadata) nor
// route_id/camera_id (shim resolution details) — docs/14 §3.
const stripModuleDropped = (o: Record<string, unknown>) => {
  const { issued_at: _i, route_id: _r, camera_id: _c, ...rest } = o; return rest;
};

// --- mission fixtures: validate + all three legs ---
for (const c of MISSIONS) {
  const [ok, reason] = validateCommonMission(c.common);
  check(`${c.name}: common validates`, ok, reason);

  const cmd = commonToCommand(c.common);
  eq(`${c.name}: commonToCommand`, cmd, c.module_command);

  if (c.module_command !== null) {
    const back = commandToCommon(c.module_command);
    eq(`${c.name}: commandToCommon round-trip`, back, stripModuleDropped(c.common));
    check(`${c.name}: commandToCommon drops module-absent fields`,
      back !== null && !('issued_at' in back) && !('route_id' in back)
      && !('camera_id' in back));
    eq(`${c.name}: command fixed-point`, commonToCommand(back), c.module_command);
  } else {
    check(`${c.name}: not module-dispatchable`, cmd === null);
  }

  const cfg: DeviceShimConfig = {
    camera_id: c.shim.camera_id,
    routes: c.shim.routes,
  };
  const r = commonToRoverMission(c.common, DEVICE, cfg, SECRET);
  check(`${c.name}: commonToRoverMission ok`, r.ok, r.ok ? '' : r.reason);
  if (r.ok) {
    eq(`${c.name}: rover mission fields`, stripSig(r.mission), c.rover_mission);
    const { signature, ...unsigned } = r.mission;
    check(`${c.name}: signature verifies`,
      signature === signMission(unsigned as Record<string, unknown>, SECRET));
    // fixed point where the rover form preserves module-required fields;
    // rover_form_lossy cases correctly refuse the second leg (docs/14 §3)
    const back2 = roverToCommon(r.mission);
    check(`${c.name}: roverToCommon`, back2 !== null);
    if (back2) {
      const r2 = commonToRoverMission(back2, DEVICE, cfg, SECRET);
      if (c.rover_form_lossy) {
        check(`${c.name}: lossy rover form refuses re-dispatch`, !r2.ok);
      } else {
        check(`${c.name}: rover round-trip fixed point`,
          r2.ok && canonicalJson(stripSig(r2.mission)) === canonicalJson(c.rover_mission));
      }
    }
  }
}

// --- validation negatives ---
{
  const base = structuredClone(MISSIONS[0].common);
  const cases: Array<[string, (m: any) => void, string]> = [
    ['bad contract', (m) => { m.contract = 'bogus'; }, 'bad_contract'],
    ['bad schema', (m) => { m.schema_version = 2; }, 'bad_schema_version'],
    ['missing mission_id', (m) => { delete m.mission_id; }, 'missing_mission_id'],
    ['unknown type', (m) => { m.type = 'launch_missiles'; }, 'unknown_type'],
    ['missing waypoint', (m) => { m.waypoint_id = ''; }, 'missing_waypoint_id'],
    ['patrol no selector', (m) => { m.type = 'patrol'; m.waypoint_id = null; m.route_id = null; },
      'missing_waypoint_id|route_id'],
    ['rescan no zone', (m) => { m.type = 'wireless_rescan'; m.zone_id = null; }, 'missing_zone_id'],
    ['bad expires', (m) => { m.expires_at = 'not-a-date'; }, 'bad_expires_at'],
    ['missing expires', (m) => { delete m.expires_at; }, 'missing_expires_at'],
    ['bad speed', (m) => { m.max_speed_mps = -1; }, 'bad_max_speed_mps'],
    ['non-ascii', (m) => { m.zone_id = 'zöne'; }, 'non-ascii field zone_id'],
  ];
  for (const [name, mutate, want] of cases) {
    const m = structuredClone(base); mutate(m);
    const [ok, reason] = validateCommonMission(m);
    check(`reject ${name}`, !ok && reason === want, `got ${reason}`);
  }
  // module window enforced only at module leg
  const fast = structuredClone(base); fast.max_speed_mps = 0.9;
  check('common accepts speed 0.9', validateCommonMission(fast)[0]);
  check('module leg rejects speed 0.9', commonToCommand(fast) === null);
  const edge = structuredClone(base); edge.max_speed_mps = 0.5;
  check('module leg accepts speed 0.5', commonToCommand(edge) !== null);
  // device mismatch rejected at rover leg
  const r = commonToRoverMission(base, 'other-device',
    { camera_id: 'cam-mast', routes: {} }, SECRET);
  check('device mismatch rejected', !r.ok);
}

// --- module state projection table (docs/14 §4) ---
{
  const want: Record<string, [string, string] | null> = {
    accepted: ['accepted', 'accepted'],
    navigating: ['navigating', 'navigating'],
    scanning: ['navigating', 'scanning'],
    completed: ['completed', 'completed'],
    failed: ['failed', 'failed'],
    aborted: ['failed', 'aborted'],
    timed_out: ['failed', 'timed_out'],
    queued: null, proposed: null, approved: null, dispatched: null,
    expired: null, cancelled: null,
  };
  for (const [state, exp] of Object.entries(want)) {
    const got = moduleReportFields(state);
    if (exp === null) check(`report ${state} -> null`, got === null);
    else eq(`report ${state}`, got, { state: exp[0], reason: exp[1] });
  }
  eq('aborted keeps native reason', moduleReportFields('aborted', 'estop_asserted'),
    { state: 'failed', reason: 'aborted:estop_asserted' });
  check('STATE_TO_MODULE_DEVICE table sane',
    Object.keys(STATE_TO_MODULE_DEVICE).length === 13);
}

// --- telemetry fixtures ---
for (const c of TELEMETRY.filter((t: any) => 'rover_event' in t)) {
  const got = roverEventToCommon(c.rover_event, c.provenance as Provenance);
  eq(`${c.name}: roverEventToCommon`, got, c.common);
  check(`${c.name}: telemetry validates`,
    got !== null && validateCommonTelemetry(got)[0]);
}
for (const c of TELEMETRY.filter((t: any) => 'autonomy_report' in t)) {
  const got = autonomyReportToCommon(
    c.autonomy_report, c.device_id, c.provenance as Provenance, c.observed_at);
  eq(`${c.name}: autonomyReportToCommon`, got, c.common);
  check(`${c.name}: telemetry validates`,
    got !== null && validateCommonTelemetry(got)[0]);
}
{
  const base = structuredClone(TELEMETRY[0].common);
  const badState = { ...base, state: 'exploded' };
  check('reject bad state', validateCommonTelemetry(badState)[0] === false);
  const badProv = { ...base, provenance: 'SIM' };
  check('reject bad provenance', validateCommonTelemetry(badProv)[1] === 'bad_provenance');
  const badPose = { ...base, pose: { x: 1, y: 2 } };
  check('reject bad pose', validateCommonTelemetry(badPose)[1] === 'bad_pose');
}

// --- evidence fixtures ---
for (const c of EVIDENCE) {
  const got = evidenceToCommon(c.evidence, { device_id: c.device_id });
  eq(`${c.name}: evidenceToCommon`, got, c.common);
  if (c.common !== null) {
    check(`${c.name}: evidence validates`,
      got !== null && validateCommonEvidence(got)[0]);
  }
  if (c.module_row !== null) {
    eq(`${c.name}: module evidence row`,
      commonToModuleEvidenceRow(c.common, {
        incident_id: c.module_row.incident_id,
        trust_tier: c.module_row.trust_tier,
        trace_id: c.module_row.trace_id,
      }), c.module_row.expected);
  }
}

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);
