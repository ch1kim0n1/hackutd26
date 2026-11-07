#!/usr/bin/env bash
# Acceptance evidence harness — runs every software-verifiable check for the
# FINALIZE gates (#39-#47) and writes a signoff packet reviewers can audit.
#
# Hardware-only evidence (waypoint patrols, E-stop, physical wiring, demo
# video) is intentionally NOT produced here — it requires the physical lab.
# The report marks those items HUMAN-REQUIRED so reviewers see exactly what
# remains.
#
# Usage: deploy/scripts/run-acceptance.sh [output-dir]
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="${1:-$REPO_ROOT/deploy/evidence/$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "$OUT/logs"
cd "$REPO_ROOT"

pass=0; fail=0
declare -a RESULTS

run() {
  local name="$1"; shift
  local log="$OUT/logs/${name}.log"
  echo "=== $name ==="
  if "$@" > "$log" 2>&1; then
    pass=$((pass+1)); RESULTS+=("PASS|$name")
    tail -1 "$log" | sed 's/^/  /'
  else
    fail=$((fail+1)); RESULTS+=("FAIL|$name")
    echo "  FAILED — see $log"
  fi
}

run_py() { # package dir, pytest target
  (cd "$2" && PYTHONPATH=src python3 -m pytest "${3:-tests}" -x -q) >> "$OUT/logs/$1.log" 2>&1
}

# ---------- package test suites ----------
PY_PKGS=(
  sensors/pucks sensors/correlator sensors/sdr robotics/rover
  apps/agent/nemotron_client apps/agent/investigator apps/agent/hardening
  apps/containment/policy apps/containment/executor apps/containment/audit
  apps/control_plane apps/identity apps/security_tests
  apps/incident_records apps/scope_matrix apps/incident_chat
  apps/glue/vertical_slice apps/glue/correlation_agent
  apps/glue/rover_mission apps/glue/twin_feed apps/glue/closed_loop
  apps/glue/acceptance apps/ops/chaos_harness apps/dashboard/rf_intel
)
# (pkg, pytest target) pairs for packages without a tests/ dir
PY_ROOT_TESTS=(
  "apps/ops/demo:test_demo.py"
  "apps/dashboard/ops_ux:test_ux.py"
)
for pkg in "${PY_PKGS[@]}"; do
  name="pytest-${pkg//\//_}"
  echo "=== $name ==="
  if run_py "$name" "$pkg"; then
    pass=$((pass+1)); RESULTS+=("PASS|$name")
    tail -1 "$OUT/logs/$name.log" | sed 's/^/  /'
  else
    fail=$((fail+1)); RESULTS+=("FAIL|$name"); echo "  FAILED — see $OUT/logs/$name.log"
  fi
done
for pair in "${PY_ROOT_TESTS[@]}"; do
  pkg="${pair%%:*}"; tgt="${pair##*:}"
  name="pytest-${pkg//\//_}"
  echo "=== $name ==="
  if run_py "$name" "$pkg" "$tgt"; then
    pass=$((pass+1)); RESULTS+=("PASS|$name")
    tail -1 "$OUT/logs/$name.log" | sed 's/^/  /'
  else
    fail=$((fail+1)); RESULTS+=("FAIL|$name"); echo "  FAILED — see $OUT/logs/$name.log"
  fi
done

# ---------- TS unit suites (no external deps) ----------
run gateway-validate sh -c 'cd services/gateway && npx tsx test/validate.test.ts'
run mission-shim-transform sh -c 'cd services/mission-shim && npx tsx test/transform.test.ts'
run gateway-tsc sh -c 'cd services/gateway && npx tsc --noEmit'
run mission-shim-tsc sh -c 'cd services/mission-shim && npx tsc --noEmit'
run spacetimedb-build sh -c 'cd spacetimedb && npm run build'

# ---------- cross-language e2e: shim signature -> rover validate ----------
run shim-to-rover-e2e sh -c '
  set -e
  TSX=services/mission-shim/node_modules/.bin/tsx
  [ -x "$TSX" ] || TSX=npx\ tsx
  cat > /tmp/sh-acc-gen.ts <<'GEN'
import { transformCommand } from "'"$REPO_ROOT"'/services/mission-shim/src/transform.js";
import { writeFileSync } from "node:fs";
const cmd = {schema_version:1, command_id:"mis-acc", mission_id:"mis-acc",
  device_id:"rover-01", type:"inspect_zone", zone_id:"rack-01",
  waypoint_id:"wp-rack-a",
  expires_at:new Date(Date.now()+600000).toISOString(), max_speed_mps:0.2};
const r = transformCommand(cmd, "rover-01", {routes:{"*":"patrol-main"}}, "acc-secret");
if (!r.ok) { console.log("FAIL", r.reason); process.exit(1); }
writeFileSync("/tmp/sh-acc-mission.json", JSON.stringify(r.mission));
GEN
  npx tsx /tmp/sh-acc-gen.ts
  cd robotics/rover
  ROVER_MISSION_SECRET=acc-secret PYTHONPATH=src python3 -m rover_mission \
    validate /tmp/sh-acc-mission.json | grep -q "\"valid\": true"
'

# ---------- executor service e2e (HTTP -> VERIFIED) ----------
run executor-service-e2e sh -c '
  cd apps/containment/executor
  PYTHONPATH=src EXECUTOR_PORT=18099 EXECUTOR_TOKEN=acc python3 \
    -c "
import json, subprocess, time, urllib.request, urllib.error, os, sys
proc = subprocess.Popen([sys.executable, \"-m\", \"containment_executor.service\"],
    env={**os.environ, \"PYTHONPATH\": \"src\"},
    stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
try:
    for _ in range(50):
        try:
            urllib.request.urlopen(\"http://127.0.0.1:18099/healthz\", timeout=0.5)
            break
        except Exception:
            time.sleep(0.1)
    doc = {\"schema_version\":1,\"action_id\":\"acc-1\",\"incident_id\":\"inc-1\",
           \"type\":\"isolate_endpoint\",\"target_id\":\"lab-ep-1\",
           \"fingerprint\":\"fp\",\"approval_id\":\"appr-1\"}
    req = urllib.request.Request(\"http://127.0.0.1:18099/execute\",
        data=json.dumps(doc).encode(), method=\"POST\",
        headers={\"content-type\":\"application/json\",
                 \"authorization\":\"Bearer acc\"})
    with urllib.request.urlopen(req, timeout=5) as r:
        body = json.loads(r.read())
    assert r.status == 200 and body[\"state\"] == \"verified\", body
    print(\"VERIFIED:\", body[\"states\"])
finally:
    proc.terminate(); proc.wait()
"
'

# ---------- report ----------
REPORT="$OUT/report.md"
{
  echo "# Acceptance evidence — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo
  echo "commit: $(git rev-parse --short HEAD)  branch: $(git rev-parse --abbrev-ref HEAD)"
  echo
  echo "| check | result |"
  echo "|-------|--------|"
  for r in "${RESULTS[@]}"; do
    IFS='|' read -r st nm <<< "$r"
    echo "| $nm | $st |"
  done
  echo
  echo "**Summary: $pass passed, $fail failed**"
  echo
  echo "## HUMAN-REQUIRED items (not verifiable by this harness)"
  echo "- HW: physical patrol runs, E-stop/watchdog demos, wiring/BOM photos,"
  echo "  power integrity measurements (issue #39)"
  echo "- All subsystems: reviewer signoff + screenshot/video evidence"
  echo "- GLUE-07: 3 consecutive live 90s runs; GLUE-08: fresh-host deploy +"
  echo "  judge demo video"
} > "$REPORT"

echo
echo "==> $pass passed, $fail failed"
echo "==> report: $REPORT"
[ "$fail" -eq 0 ]
