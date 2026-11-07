# Data Contracts and SpacetimeDB

## Schema (conceptual, implement in installed SpacetimeDB TS SDK)
Tables: devices(id,type,zone,status,last_seen,firmware); zones(id,name,bounds,waypoints); assets(id,zone,type,owner,authorized_network_ids); observations(id,device_id,kind,seq,observed_at,received_at,zone_id,data_json,trust_tier); alerts(id,rule_id,observation_ids,severity,state); incidents(id,title,description,severity,confidence,status,commander_id,created_at,updated_at,version); evidence(id,incident_id,source,observed_at,storage_ref,sha256,trust_tier); missions(id,incident_id,device_id,waypoint,state,expiry); scope_entries(id,incident_id,asset_id,dataset_category,impact_dimensions,impact_statuses,estimated_records,evidence_refs,reviewer); actions(id,incident_id,type,target_id,initiator,approval_id,fingerprint,state,verification_ref); approvals(id,actor_id,action_id,expires_at,decision); users_and_roles(user_id,role,incident_scope,revoked); chat_messages(id,incident_id,sender,body,created_at,client_nonce); audit_events(id,actor,operation,entity,before_hash,after_hash,at,trace_id); rf_frames(id,receiver,kind,at,artifact_ref); health(component,status,last_seen).

## Canonical event payload
JSON example:
{"schema_version":1,"event_id":"evt-1024","device_id":"puck-a-01","seq":194,"observed_at":"2026-11-07T20:00:00Z","kind":"wifi_ap_seen","zone_id":"rack-01","data":{"ssid":"SENTINEL-CORP","bssid":"02:AA:BB:CC:DD:01","channel":6,"rssi_dbm":-48}}

Gateway adds authenticated source principal, received_at and schema validation; reject duplicate ID, stale/replayed sequence, oversized packet, invalid kind and unknown device. Never trust user-supplied principal fields for authorization.

## Rover mission contract
{"schema_version":1,"command_id":"cmd-042","mission_id":"mission-042","device_id":"rover-01","type":"inspect_zone","zone_id":"rack-01","waypoint_id":"tag-rack-01","expires_at":"2026-11-07T20:05:00Z","max_speed_mps":0.25}
Strict enums and waypoint whitelist; robot reports accepted, navigating, completed/failed with matching IDs; no arbitrary PWM fields.

## Reducers / transaction rules
ingestObservation -> raiseAlert -> createIncident -> attachEvidence -> assignMission -> recordMissionResult -> proposeAction -> recordApproval -> enqueueApprovedAction -> recordExecutorOutcome -> verifyContainment -> updateScope -> closeIncident.
Reducers are atomic transactions and must verify role, incident scope, expected_version, actor identity, action lifecycle and bounded payload. **External commands must run in independent outbox worker, never as DB transaction side effects.**

## Role matrix
Admin: add/revoke and set roles; Commander: incident control and scoped approval; Responder: investigate, notes, evidence, chat, propose; Observer: scoped read-only; Agent: bounded tool service, propose, no approval; Device: ingest its own telemetry only; Executor: strictly approved action state transitions. Identity comes from server-side authenticated context, not frontend claims. Separation of duties for high-impact actions.

## Incident and scope types
Incident states: new, triage, investigating, containment_pending, contained, recovery, resolved, closed, dismissed.
Impact dimensions: confidentiality, integrity, availability.
Scope statuses (can apply multiple): unknown, suspected_exposed, confirmed_exposed, exfiltrated, encrypted_locked, corrupted, unavailable, contained, restored, unaffected.
Track asset/dataset/category, estimated affected records, impact window, evidence, confidence, reviewer and previous snapshots. 'Unknown' never means unaffected. Agent inference not equal to confirmed fact.

## RF contracts
Wi-Fi observation: ssid,bssid,channel,rssi_dbm,source_id,observed_at.
SDR FFT frame: center_frequency_hz,sample_rate_hz,fft_size,bin_width_hz,dbfs_bins[],window_type,receiver_id,observed_at,source_mode (live/replay/synthetic).

## Realtime and security
Private source tables; role-scoped views or trusted projection gateway for subscriptions. Do not leak privileged cross-incident rows. Evidence binary stored separately with short-lived authenticated URLs. Chat rooms and presence permission-checked. Client_nonce and action fingerprint guarantee idempotency; version checks prevent silent overwrite. Use UTC, explicit provenance and trace IDs.
