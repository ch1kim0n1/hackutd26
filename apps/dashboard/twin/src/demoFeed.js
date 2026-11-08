// Demo feed - stands in for TwinFeed/SpacetimeDB until live backend
// is wired. Same contract: subscribe(principal)->sub_id,
// stream(sub_id)->FeedItem[]. All data SIMULATED, provenance labeled.
// Incident markers derive from the fictional Meridian Datacenters
// dataset (mock/company.ts).
import { incidents as COMPANY_INCIDENTS, zones as COMPANY_ZONES } from './mock/company.ts'

const ZONE_CENTERS = Object.fromEntries(
  COMPANY_ZONES.map((z) => [z.id, { x: z.bounds.x + z.bounds.w / 2, z: z.bounds.y + z.bounds.d / 2 }])
)
const INCIDENTS = COMPANY_INCIDENTS.filter((i) => i.status !== 'resolved').map((i) => ({
  incident_id: i.id, title: i.title, severity: i.severity,
  x: ZONE_CENTERS[i.zoneId]?.x ?? 0, z: ZONE_CENTERS[i.zoneId]?.z ?? 0,
}))

export class DemoFeed {
  constructor() {
    this.t0 = Date.now();
    this.subs = new Set();
  }
  subscribe(principal) {
    const sid = `demo-${this.subs.size + 1}`;
    this.subs.add(sid);
    return sid;
  }
  stream(sid) {
    const t = (Date.now() - this.t0) / 1000;
    const items = [];
    // rover patrols a rounded loop - pose is "telemetry"
    const px = 3 * Math.cos(t / 12);
    const pz = 3 * Math.sin(t / 12);
    const stale = t > 30 && Math.floor(t / 10) % 2 === 0; // intermittent stale demo
    items.push({ kind: "rover_pose", ref_id: "rover-1",
      at: Date.now(), provenance: "SYNTHETIC", stale,
      payload: { x: px, y: 0, z: pz, heading: Math.atan2(-pz, px) + Math.PI / 2 } });
    for (const inc of INCIDENTS) {
      items.push({ kind: "incident_marker", ref_id: inc.incident_id,
        at: Date.now(), provenance: "SYNTHETIC", stale: false,
        payload: { incident_id: inc.incident_id, title: inc.title,
                   x: inc.x, z: inc.z, severity: inc.severity,
                   evidence_id: `ev-${inc.incident_id}` } });
    }
    items.push({ kind: "rf_scan", ref_id: `scan-${Math.floor(t / 5)}`,
      at: Date.now(), provenance: "SYNTHETIC", stale: false,
      payload: { channels: { 1: -62, 6: -48, 11: -71 },
                 bssid: "aa:bb:cc:dd:ee:ff", rssi_dbm: -48,
                 note: "demo scan - not a real measurement" } });
    return items;
  }
}
