# BlindSpot visual kit

Presentation-ready images and diagrams based on the repository's design documents and implementation notes. The 2D vector-style illustrations are AI-generated raster concept art, not photographs or screenshots of the system. The team’s reference photos show an assembled rover prototype; the detailed hardware design and its test status have not been verified from those photos. The frontend demo is simulated; it is not yet connected to the separate live integration path.

## Use the visuals

| Asset | Use | Source formats |
|---|---|---|
| [BlindSpot Devpost banner](blindspot-devpost-banner.png) | 3:2 Devpost gallery thumbnail and README hero | PNG |
| [High-level overview](05-blindspot-overview.svg) | Hackathon slide with workflow and stack logos | [SVG](05-blindspot-overview.svg) · [PNG](05-blindspot-overview.png) |
| [Software and hardware architecture](06_blindspot_architecture.svg) | Judge-ready operating loop with trust boundaries and validation status | [SVG](06_blindspot_architecture.svg) · [PNG](06_blindspot_architecture.png) |
| [Hero concept](hero-concept.png) | README cover or opening slide | PNG |
| [Incident response concept](incident-response-concept.png) | 2D scene for a system overview | PNG |
| [Hardware concept](hardware-concept.png) | Illustrate the rover prototype and conceptual sensor pucks | PNG |
| [Project flow](01-project-flow.svg) | End-to-end intended workflow | [SVG](01-project-flow.svg) · [PNG](01-project-flow.png) |
| [Software flow](02-software-flow.svg) | Compare the current demo and separate integration path | [SVG](02-software-flow.svg) · [PNG](02-software-flow.png) |
| [Hardware flow](03-hardware-flow.svg) | Explain intended sensing, motion, power and safety | [SVG](03-hardware-flow.svg) · [PNG](03-hardware-flow.png) |
| [Evidence graph](04-evidence-graph.svg) | Explain provenance, decisions and verification | [SVG](04-evidence-graph.svg) · [PNG](04-evidence-graph.png) |

The AI-generated illustrations are PNGs in a flat vector style; the diagrams are editable SVGs with PNG exports. The diagrams are 16:9. The high-level overview and architecture flow PNGs are 1920 × 1080; the other diagram PNGs are 1600 × 900. SVGs can be scaled or edited as vectors. The conceptual graph does not invent performance measurements. To change diagram content and regenerate both formats, edit `generate_diagrams.py` and run `python3 docs/visuals/generate_diagrams.py` with CairoSVG installed. For the overview, run `python3 docs/visuals/generate_presentation_overview.py`. For the architecture flow, run `python3 docs/visuals/generate_architecture_flow.py`.

## Sources and limits

- [Architecture and trust boundaries](../01-SYSTEM-ARCHITECTURE.md)
- [Proposed hardware and electrical design](../02-HARDWARE.md) and [hardware status](../../hardware/README.md)
- [Rover and RF constraints](../03-ROBOTICS-RF.md)
- [Phantom Command simulation](../../apps/dashboard/twin/README.md)
- [Separate local integration runbook](../15-DEVELOPER-RUNBOOK.md)

Human approval is required for disruptive lab response; the agent has no direct motor or containment authority. The diagrams describe intended relationships, not proof that all components are connected or tested. The illustrations use the team’s rover photographs as visual references; sensor pucks and setting are conceptual. They intentionally simplify physical details and should not be used as assembly or wiring references.

## Logo credits

The technology marks for React, TypeScript, Three.js, Python, FastAPI, C++, Espressif, MQTT and NVIDIA are from [Simple Icons](https://github.com/simple-icons/simple-icons) (CC0; brand marks remain the property of their respective owners). The SpacetimeDB mark is from the [official SpacetimeDB repository](https://github.com/clockworklabs/SpacetimeDB/blob/master/images/dark/logo.svg). Logo placement identifies project technologies and does not imply endorsement.

## Image generation prompts

Created and revised with the built-in image generation tool. The revision used the team’s photographs as references for the four-wheel chassis, white hubs, raised LiDAR, front camera, twin round sensors, and exposed electronics. Prompt summaries:

- **BlindSpot Devpost banner:** 3:2 flat 2D vector-style project banner with the exact title BlindSpot, a photo-referenced inspection rover in a server-room lab, subtle cyan spatial and network signals, dark navy and restrained amber; concept art.

- **Hero:** Flat 2D vector-style photo-referenced indoor security rover with raised LiDAR and a front camera in a server-room mockup, sensor pucks, navy/cyan lighting, amber accents, and open space for a title; concept art without text or logos.
- **Incident response:** Flat 2D vector-style rover inspecting a server cabinet in an office lab, with subtle spatial-map and network visualizations, dark graphite/cyan/amber palette; conceptual scene without text or logos.
- **Hardware:** Flat 2D vector-style four-wheel rover based on the reference photos with raised LiDAR, front camera and sensors, accompanied by three conceptual pucks; polished concept, not a wiring reference.
