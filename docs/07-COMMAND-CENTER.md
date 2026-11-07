# Command Center UI: Digital Twin, RF Intelligence and Winstead Workflows

## Overall UI
Four primary views: **Command** (incident queue, status, response CTA); **Digital Twin** (3D spatial telemetry); **Spectrum** (Wi-Fi channel activity, optional true SDR waterfall); **Incidents** (documentation, impact scope, evidence, chat, approvals). Admin has separate user-management view. Incident deep links preserve selected event and filtered timeline. Default screen is actionable queue, not 3D decoration.

## Stack
React + TypeScript + Vite; Three.js + React Three Fiber for scene; accessible components for incident workflows; SpacetimeDB subscriptions or server-authorized projection stream; protected object store for image evidence. All critical state derives from subscriptions rather than fake local timers.

## A. Digital Twin
- Measured compact office model: floor, desks, cabinet/rack, AP, pucks. Axes correspond to known survey (meters) with origin marked.
- Render robot pose, heading, pose timestamp, confidence, battery and live planned/done route; differentiate stale pose.
- Render puck health, cabinet state and RF anomaly icon attached to zone. Incident severity reflected with accessibility-compatible color + text/icon, not color alone.
- Click alert or asset -> open drawer with incident title/state, evidence photo thumbnail, timestamp, authorized radio observations, device provenance, Nemotron investigation steps, pending actions and link to full incident.
- Click robot -> mission, route, E-stop/fault state; UI cannot bypass the bounded mission gateway.
- Playback scrubber uses historical timestamped events with visible LIVE/REPLAY indicator; never show synthesized positions as live GPS.

## B. RF Spectrum Intelligence
RF console has **Wi-Fi Channel Activity** tab (P0) with 2.4 GHz channels, AP appearances, RSSI trend and unknown/authorized BSSID classification. Use ESP32 scan or Kismet metadata; label this a channel heatmap, NOT a raw spectrum waterfall.

**SDR Waterfall** tab (P1) available only when an actual supported SDR receiver and IQ FFT pipeline exist. Horizontal axis frequency MHz; vertical axis time UTC; heatmap color relative dBFS power. Show center frequency, sample rate, fft_size, receiver, mode LIVE/REPLAY/SYNTHETIC, last updated, health. rtl_433 provides specific sub-GHz decoded messages but cannot replace IQ spectra; generic RTL-SDR does not capture 2.4 GHz Wi-Fi. If no SDR, explicitly disable this tab with an explanation rather than fabricate data.

Link a selected radio event to zone, source, incident ID and evidence provenance. RF estimate should not claim absolute localization from RSSI alone; use zone-level confidence and multiple measurements.

## C. Winstead incident workflow (highest priority)
- **Isolation:** management-plane UI independent from the office lab; live isolation/health indicator and no office-side admin session reliance.
- **Access control:** Admin can add, revoke, assign role and restrict incident scope; users can see their role; every operation is audited and enforced server-side.
- **Documentation:** Create/update incident, status, owner, severity, first/last timestamps, structured timeline, evidence attachment, actions/proposals, notes, export; NIST-inspired fields.
- **Compromised data scope:** Dedicated impact tab with asset, dataset category, records estimated, C/I/A dimension, suspected vs confirmed, exfiltrated, encrypted/locked, containment, restored, confidence, last update. Show unknown as unknown.
- **Real-time communication:** Incident-scoped chat with timestamps, authorized roles, unread/presence/reconnect, system status updates; two users see messages without refresh.
- **Ease under stress:** queue -> open incident -> see impact scope -> chat -> approve in <= 2 clicks for common tasks; large visible primary action, minimal teaching required, confirmation for disruptive actions. No automatic approval.

## Main layout
Desktop >=1280px: left collapsible incident list; center 3D twin or tabbed RF view; right incident details + context actions; bottom timeline/chat tabs. Tablet/narrow screen: incident list first, responsive one-panel view with persistent critical actions. Keyboard navigation, semantic labels, readable contrast and clear error messages.

## 3D scene integration
Scene model is static authored GLB from Blender/primitive meshes for 24h MVP. SpacetimeDB carries dynamic waypoint and telemetry; R3F renders glTF and instanced sensors. Use a single authoritative world-coordinate mapping. Rate-limit pose subscriptions to useful interval (e.g. 2–10 Hz) and interpolate visually only between **real** measured poses, with visible stale cutoff. Do not animate a fake path during a failed mission.

## Evidence drawer
Selected alert shows actual camera image from authenticated evidence service (not public URL); Wi-Fi source metadata, signal observations/channel plot or IQ frame ref; timeline in UTC with local display toggle; Nemotron tool trace and hypothesis list; confidence and gaps; operator annotations; action approval/outcome. Every evidence item displays source and acquisition timestamp.

## UI acceptance
U01 new responder without tutorial opens incident, locates scope and sends message within 60s; U02 3D robot follows authenticated telemetry, stale/disconnect shown; U03 clicked threat opens actual image and RF provenance; U04 live subscriptions update simultaneously on two clients; U05 observer sees only approved incident, cannot mutate; U06 no visual conflation of Wi-Fi channel heatmap and FFT; U07 no nonexistent data marked live; U08 incident export contains timeline/scope/evidence refs; U09 admin add/revoke visible UI; U10 disconnected lab does not block independent dashboard navigation/chat.

## Design system
Dark SOC theme with accessible high contrast; color roles: muted gray normal, amber investigation, red critical, blue containment, green independently verified resolution. Use explicit labels and severity text; never rely on color alone. Avoid decorative graphs lacking source/provenance.
