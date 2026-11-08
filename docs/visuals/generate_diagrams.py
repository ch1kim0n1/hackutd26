#!/usr/bin/env python3
"""Generate editable SVGs and presentation-ready PNGs from the documented design."""
from pathlib import Path
from html import escape
import cairosvg

OUT = Path(__file__).resolve().parent
W,H=1600,900

def text(x,y,s,size=22,color='#dbeaf2',weight=400):
    return f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" font-weight="{weight}">{escape(s)}</text>'
def card(x,y,w,h,k,title,lines,accent='#50d9e6'):
    s=f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="15" fill="#122331" stroke="#294858" stroke-width="2"/><rect x="{x}" y="{y}" width="6" height="{h}" rx="3" fill="{accent}"/>'
    s+=text(x+24,y+30,k.upper(),15,accent,700)+text(x+24,y+65,title,25,'#f2f8fb',700)
    for i,l in enumerate(lines): s+=text(x+24,y+96+i*26,l,18,'#b8cdd8')
    return s
def arrow(path,color='#64d4df',dashed=False):
    return f'<path d="{path}" fill="none" stroke="{color}" stroke-width="3" {"stroke-dasharray=\"7 6\"" if dashed else ""} marker-end="url(#arrow)"/>'
def base(title,sub,body,foot):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{escape(title)}">
<defs><linearGradient id="bg" x2="1" y2="1"><stop stop-color="#08121d"/><stop offset="1" stop-color="#101d29"/></linearGradient><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#64d4df"/></marker></defs>
<rect width="{W}" height="{H}" fill="url(#bg)"/><path d="M0 145 H1600" stroke="#294858"/>
<g font-family="Inter, Arial, sans-serif">{text(64,52,'BLINDSPOT  /  VISUAL FIELD GUIDE',16,'#63dce8',700)}{text(64,95,title,37,'#f3f9fc',700)}{text(64,124,sub,19,'#a9c0cc')}{body}<path d="M64 837 H1536" stroke="#294858"/>{text(64,865,foot,16,'#9eb4c0')}</g></svg>'''
def save(name,title,sub,body,foot):
    svg=base(title,sub,body,foot)
    (OUT/f'{name}.svg').write_text(svg)
    cairosvg.svg2png(bytestring=svg.encode(),write_to=str(OUT/f'{name}.png'),output_width=1600,output_height=900)

# End-to-end concept: labels distinguish observed, inference, human decision and verification.
b=''
xs=[64,576,1088]; w=448; h=150
items=[('01 / observe','Sense the lab',['Wi-Fi + cabinet observations','Rover and other sensor inputs']),('02 / correlate','Create an incident',['Validate and normalize events','Link related observations']),('03 / investigate','Investigate evidence',['Agent uses bounded tools','Request a safe rover mission']),('06 / document','Verify and record',['Verify outcome independently','Update timeline, scope and chat']),('05 / decide','Human approval',['Authorized operator review','Scoped, lab-only response']),('04 / inspect','Collect evidence',['Rover visits a known waypoint','Evidence and status reach the twin'])]
for i,(k,t,ls) in enumerate(items):
    row=i//3; col=i%3
    b+=card(xs[col],240+row*280,w,h,k,t,ls,'#f0b35f' if i==4 else '#50d9e6')
for p in ['M512 315 H570','M1024 315 H1082','M1510 390 V452 H1312 V514','M1088 595 H1030','M576 595 H518']:
    b+=arrow(p)
b+=text(65,735,'Design goal: an independent command plane remains outside the untrusted office lab.',20,'#a9c0cc')
save('01-project-flow','How the project works','End-to-end concept  •  intended system, with simulation available today',b,'Conceptual workflow • live hardware and end-to-end integration require verification')

b=''
b+=text(64,195,'AVAILABLE NOW  /  PHANTOM COMMAND',16,'#6de1d9',700)
software=[('SIMULATED INPUT','Scenario + observations',['Deterministic fixtures','Synthetic events and telemetry']),('SIMULATION ENGINE','Correlate + investigate',['Mock agent and policy decisions','Bounded simulated rover mission']),('SHARED INTERFACE','Present + resolve',['In-memory shared state','Twin, incident, RF and rover views']),('INTEGRATION PATH','Device + gateway',['MQTT, validation, normalization','Device observations to reducers']),('STATE + INVESTIGATION','SpacetimeDB + agent',['Transactional state and feeds','Nemotron or configured fake']),('COMMAND + RESPONSE','Operator + executor',['Human approval for lab actions','Verify and audit outcome'])]
for i,(k,t,ls) in enumerate(software):
    row=i//3; col=i%3
    b+=card(xs[col],225+row*300,w,150,k,t,ls,'#f0b35f' if row else '#50d9e6')
for y in (300,600):
    b+=arrow(f'M512 {y} H570')+arrow(f'M1024 {y} H1082')
b+=text(64,493,'SEPARATE INTEGRATION PATH  /  NOT CONNECTED TO THE FRONTEND DEMO',16,'#f0b35f',700)
b+=text(64,766,'The demo uses no live hardware, backend or model calls. Integration pieces have their own runbooks.',19,'#a9c0cc')
save('02-software-flow','How the software works','Two paths: the runnable local demo and the separately integrated stack',b,'Current status from apps/dashboard/twin/README.md and docs/15-DEVELOPER-RUNBOOK.md')

b=''
for yy,label in [(193,'SENSING + EVIDENCE'),(393,'MOTION + LOCAL SAFETY'),(593,'POWER + INDEPENDENT STOP')]: b+=text(64,yy,label,16,'#65dce8',700)
rows=[
 [('LAB DEVICES','Pucks + rover',['Wi-Fi, cabinet and BLE inputs','Camera connects to rover Pi']),('LOCAL COLLECTION','Pi + sensor pucks',['Pucks publish observations','Pi collects rover evidence']),('UPLINK','Gateway + command',['Relay observations and status','Gateway validates device events'])],
 [('MISSION INPUT','Bounded intent',['Surveyed waypoints and speed cap','No model-controlled raw motors']),('MOTOR CONTROL','ESP32 controller',['Watchdog and obstacle stop','Commands motor driver']),('PHYSICAL DRIVE','Driver + motors',['Encoders return motion feedback','Wheels move the rover'])],
 [('SUPPLY','Protected battery',['Fuse and master switch','Separate compute and motor rails']),('MOTOR RAIL','Physical E-stop',['Accessible independent stop','Interrupts motor power']),('COMPUTE RAIL','Pi regulator',['Dedicated regulated supply','Separate from motor power'])]
]
for row,group in enumerate(rows):
    y=210+row*200
    for col,(k,t,ls) in enumerate(group): b+=card(xs[col],y,w,145,k,t,ls,'#f0b35f' if row==2 and col==1 else '#50d9e6')
    if row<2: b+=arrow(f'M512 {y+72} H570')+arrow(f'M1024 {y+72} H1082')
    else:
        b+=arrow(f'M512 {y+55} H570')
        b+=arrow(f'M290 {y+145} V{y+168} H1312 V{y+145}')
b+=arrow('M800 610 V580 H1312 V560')
b+=text(64,808,'Final wiring depends on purchased parts; local safety behavior and electrical tests remain unverified.',18,'#b9cbd5')
save('03-hardware-flow','How the hardware is intended to work','Proposed rover, sensor, power and safety architecture',b,'PROPOSED ARCHITECTURE • rover prototype photographed; wiring and tests not verified')

b=''
labels=[('01 / observed','Sensor observations',['Measurements + timestamps','Source and provenance']),('02 / derived','Correlation',['Rules link observations','A relationship, not proof']),('03 / inferred','Agent hypothesis',['Evidence-backed hypothesis','Alternatives and uncertainty']),('04 / approved','Human decision',['Authorized operator review','Scope is limited to the lab']),('05 / verified','Outcome',['Independent result check','Recorded in incident timeline'])]
for i,(k,t,ls) in enumerate(labels):
    x=64+i*304
    b+=card(x,305,270,170,k,t,ls,'#f0b35f' if i==3 else '#50d9e6')
    if i<4: b+=arrow(f'M{x+270} 390 H{x+298}')
b+=text(64,595,'Keep LIVE, REPLAY and DEMO provenance visible. A wireless anomaly alone does not prove exfiltration.',21,'#b9cbd5')
b+=text(64,641,'This is a conceptual evidence graph, not a measured performance chart.',19,'#8fa9b7')
save('04-evidence-graph','From signal to decision','Evidence provenance and decision boundaries across the workflow',b,'Conceptual graph • no numerical performance claims')
