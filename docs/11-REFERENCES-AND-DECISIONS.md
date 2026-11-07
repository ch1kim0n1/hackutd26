# References, Decisions and Open Questions

## Authoritative challenge sources
- User-provided HackUTD 2026 sponsor slides for NVIDIA Nemotron (beyond chatbot, multi-step tools, real-world usefulness), Winstead Cyber Incident Response Dashboard (five hard requirements + three judging criteria), and SpacetimeDB main track (primary system functionality beyond chat/player movement). Full Winstead transcription and acceptance requirements are maintained in 06-WINSTEAD-COMPLIANCE.md.
- These slide photos are not automatically published in GitHub; transcriptions here are planning notes, not sponsor certification. Recheck official event rules before submissions or multi-track claiming.

## Technology references to validate against pinned versions
- SpacetimeDB documentation: https://spacetimedb.com/docs
- SpacetimeDB TypeScript docs and client subscriptions: https://spacetimedb.com/docs
- NVIDIA Nemotron model catalog / NVIDIA NIM: https://build.nvidia.com/ and https://docs.nvidia.com/nim/
- Raspberry Pi 5 official documentation: https://www.raspberrypi.com/documentation/
- Espressif Wi-Fi scanning / ESP-IDF: https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/
- Kismet capture sources and APIs: https://www.kismetwireless.net/docs/
- rtl_433 compatible radio decoding: https://github.com/merbanan/rtl_433
- Three.js: https://threejs.org/docs/
- React Three Fiber: https://r3f.docs.pmnd.rs/
- NIST SP 800-61 incident handling reference: https://csrc.nist.gov/pubs/sp/800/61/r3/final
- OWASP authorization reference: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html

## Firm architectural decisions
ADR-001: Independent Winstead management/control plane from lab; compromised endpoints are untrusted.
ADR-002: SpacetimeDB is authoritative transaction and subscription layer, not mere telemetry cache.
ADR-003: Rover low-level control never delegated to LLM; local ESP32 firmware handles safety.
ADR-004: Nemotron tool API schemas enforce least privilege; no direct containment credentials in agent.
ADR-005: Disruptive containment requires human approval, allowlist and independent verification.
ADR-006: Digital twin represents surveyed geometry and real timestamped state; no fake localization.
ADR-007: Distinguish Wi-Fi channel activity from true SDR IQ FFT waterfall. Never present 433MHz telemetry as 2.4GHz Wi-Fi spectrum.
ADR-008: Photo evidence binary stored outside SpacetimeDB with authenticated reference, hash and retention policy.

## Open decisions — resolve before hardware installation
- Which exact rover chassis, motors, driver, regulator, E-stop, Pi camera and ESP32 boards are physically available?
- Whether a Kismet-capable Wi-Fi capture interface, SDR and/or compatible antenna exist; which frequencies can be legally tested?
- Where the independently secured management/control plane is deployed and how independent identity is provided.
- Tested Nemotron model ID, endpoint, terms, auth and max tool latency; how to handle inference outages.
- Installed SpacetimeDB version and secure browser subscription model.
- Whether team can submit same project to all three sponsor tracks; this is unverified by the supplied slides.
- Final office model dimensions, calibration points, command center host, firewall target/verification method.
- Which engineer owns each component, security acceptance signoff and release gate.

## Do not misrepresent
Estimates are not measurements; demo fixture is not production detection; RSSI is not precise localization; open cabinet or unknown SSID is not proof of exfiltration; generated incident summary is not independent forensics; security checklist not tested is not compliance.
