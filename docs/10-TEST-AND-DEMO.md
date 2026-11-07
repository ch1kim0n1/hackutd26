# Test Matrix, Evidence Requirements and Live Demo

## Test classifications
P0 safety and Winstead security tests block demo readiness; functional tests show actual outcomes, not mocked UI; model evaluations use fixed evidence fixture and live trial; RF tests must distinguish decoded packet metadata from IQ spectra.

## Acceptance test matrix
| ID | System | Pass condition |
|---|---|---|
| H01 | Power | no reset / brownout under rover drive |
| H02 | Motor | physical E-stop and disconnected command watchdog stop motion |
| H03 | Rover | five safe patrol runs around mock office |
| H04 | Camera | actual zone-labeled photo stored with protected retrieval |
| S01 | Sensors | cabinet contact and Wi-Fi AP events are real and authenticated |
| S02 | Security | duplicate / forged telemetry rejected, no management pivot |
| D01 | SpacetimeDB | incident created via reducer; two clients update without refresh |
| D02 | SpacetimeDB | scope, audit, missions, approvals and chat are authoritative state |
| N01 | Nemotron | at least three real tool calls produce evidence-linked recommendation |
| N02 | Nemotron | prompt injection cannot approve/execute arbitrary action |
| C01 | Containment | Commander authorizes specific owned test endpoint and result verified |
| C02 | Containment | failure/replay shows failure and never double-executes |
| UI01 | Digital twin | rover pose/route/alerts reflect real state and show staleness |
| RF01 | RF | true observed Wi-Fi channel activity; if FFT displayed real IQ provenance |
| W01–W05 | Winstead | every requirement and adversarial test in 06-WINSTEAD-COMPLIANCE passes |
| UX01 | Stress | new responder finds scope, chat, critical status in 60s |

## Winstead signoff record
Create tests/evidence/WINSTEAD-RESULTS.md and record individual W01a–e, W02a–e, W03a–e, W04a–e, W05a–d as PASS / FAIL / NOT RUN, date, operator, repro, screenshot/log. Only say 'meets Winstead sponsor requirements' when all pass. Video must show compromise scenario and independent control plane. Include artifact hashes and avoid exposing credentials.

## Repeatable 90-second integrated scenario
00–10s: Start live system, show rover normal patrol and green sensor state. Indicate independent command-center connection.
10–20s: Turn on owned second same-SSID AP and open mock cabinet; sensor puck sees events.
20–35s: SpacetimeDB creates correlated incident; Nemotron checks inventory and requests rover inspection.
35–55s: Rover travels to rack waypoint, captures image; dashboard 3D route, evidence drawer and Wi-Fi channel measurements update.
55–70s: Commander and responder exchange incident chat; scope displays suspected compromised asset with **unknown data exposure**.
70–85s: Commander authorizes lab endpoint isolation; action executor verifies network restriction and records result.
85–90s: Export structured incident timeline, demonstrate management plane is independent of lab endpoint compromise.
Timestamps are storyboarding goals, NOT validated runtime measurements.

## Alternate 3-minute Winstead-focused run
Show Admin adds role; simulate compromised lab endpoint trying dashboard access (denied); initiate incident; inspect standards-inspired notes and scope (including exfiltrated and encrypted synthetic fixtures); real-time responder chat; approve/verify action; export full incident packet. Physical rover and RF support creativity only after five mandatory features.

## Failure and chaos tests
Kill lab Wi-Fi while dashboard is open; revocation mid-session; spoof client action request; replay sensor event; inject SSID with prompt instructions; block AI inference; disconnect rover; reject containment on wrong target; simulate false firewall 'success'; corrupt an evidence file; double-send chat; ensure truthfully degraded rather than green/verified.

## Metrics to record
Alert detection delay, median/p95 state latency, rover mission completion, false alarm count, tool calls per incident, model response latency and token use, UI response time, management availability under lab failure, containment verification time, and 60-second user stress test outcome. Record environment and test date.

## Submission artifacts
Devpost summary and short clear demo video; architecture diagram; real hardware wiring/part list; screenshot of control plane and 3D digital twin; scope matrix + audit export + chat; RF measurement provenance; model/tool traces; tests/evidence signoff. Never claim features implemented that are only described in docs.
