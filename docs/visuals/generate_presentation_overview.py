#!/usr/bin/env python3
"""Build a self-contained 16:9 BlindSpot overview (SVG and PNG)."""
from pathlib import Path
from html import escape
import xml.etree.ElementTree as ET
import cairosvg

P=Path(__file__).resolve().parent
logos=P/'logos'
def txt(x,y,s,size=24,color='#e8f3f8',weight=400,anchor='start'):
 return f'<text x="{x}" y="{y}" text-anchor="{anchor}" fill="{color}" font-size="{size}" font-weight="{weight}">{escape(s)}</text>'
def logo(name,x,y,color):
 root=ET.parse(logos/f'{name}.svg').getroot()
 if name=='spacetimedb':
  inner=(logos/'spacetimedb.svg').read_text().split('>',1)[1].rsplit('</svg>',1)[0]
  return f'<svg x="{x}" y="{y}" width="46" height="46" viewBox="0 0 640 640">{inner}</svg>'
 paths=[el.attrib['d'] for el in root.iter() if el.tag.endswith('path') and 'd' in el.attrib]
 return f'<g transform="translate({x} {y}) scale(1.916667)" fill="{color}">'+''.join(f'<path d="{escape(d,quote=True)}"/>' for d in paths)+'</g>'
svg=['''<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080" viewBox="0 0 1920 1080" role="img" aria-label="BlindSpot high-level system flow and technology stack"><defs><linearGradient id="bg" x2="1" y2="1"><stop stop-color="#07111b"/><stop offset="1" stop-color="#132331"/></linearGradient><marker id="arr" markerWidth="12" markerHeight="12" refX="9" refY="4" orient="auto"><path d="M0 0 L10 4 L0 8Z" fill="#58d9e5"/></marker></defs><rect width="1920" height="1080" fill="url(#bg)"/><g font-family="Inter, Arial, sans-serif">''']
svg += [txt(85,74,'BLINDSPOT  /  HACKUTD 2026',22,'#57dce7',700),txt(85,139,'From blind spot to informed response',55,'#f3faff',700),txt(85,184,'A high-level view of the intended cyber-physical security workflow',26,'#a9bfcb')]
stages=[('01','SENSE','Spot an anomaly','Sensors + rover collect','wireless and physical signals'),('02','ANALYZE','Make sense of it','Validate observations and','connect them to an incident'),('03','INVESTIGATE','Gather evidence','Agent-guided investigation','and bounded rover inspection'),('04','RESPOND','Decide and verify','Operator reviews the response;','results are recorded and checked')]
for i,(num,title,desc,l1,l2) in enumerate(stages):
 x=85+i*455
 svg += [f'<rect x="{x}" y="265" width="385" height="264" rx="18" fill="#122634" stroke="#315465" stroke-width="2"/><rect x="{x}" y="265" width="7" height="264" rx="3" fill="{ "#f2b45e" if i==3 else "#55d8e4"}"/>',txt(x+28,307,num+'  /  '+title,18,'#f0b25e' if i==3 else '#57dce7',700),txt(x+28,356,desc,29,'#f5fbfd',700),txt(x+28,405,l1,22,'#b2c8d3'),txt(x+28,437,l2,22,'#b2c8d3')]
 if i<3: svg.append(f'<path d="M{x+393} 396 H{x+445}" stroke="#58d9e5" stroke-width="4" fill="none" marker-end="url(#arr)"/>')
svg += [txt(85,602,'BUILT WITH',19,'#68dfeb',700),txt(85,640,'Languages, frameworks and platforms across the project',25,'#d8e9ef'),'<path d="M85 663 H1835" stroke="#31505f"/>']
stack=[('typescript','TypeScript','#64a6f0'),('react','React','#61dafb'),('threedotjs','Three.js','#e9f4f8'),('python','Python','#f3cd58'),('fastapi','FastAPI','#3cd9c1'),('cplusplus','C++','#79b4ed'),('espressif','ESP-IDF','#f27575'),('mqtt','MQTT','#b5a0e7'),('spacetimedb','SpacetimeDB','#f4f6fc'),('nvidia','NVIDIA','#8cd445')]
for i,(name,label,color) in enumerate(stack):
 x=85+i*175
 svg += [logo(name,x+60,700,color),txt(x+83,779,label,18,'#deedf3',600,'middle')]
svg += ['<rect x="85" y="842" width="1750" height="97" rx="12" fill="#182d3b" stroke="#31505f"/>',txt(110,879,'DEMO TODAY',16,'#58d9e5',700),txt(110,912,'Simulated sensors, rover and agent in Phantom Command.',21,'#d6e7ee'),txt(1015,879,'INTEGRATION + HARDWARE',16,'#f0b25e',700),txt(1015,912,'Separate services; physical system remains unverified.',21,'#d6e7ee'),txt(85,1016,'Architecture concept  •  Nemotron inference is configurable; the frontend demo uses a mock agent.',18,'#90aab7'),'</g></svg>']
data=''.join(svg)
(P/'05-blindspot-overview.svg').write_text(data)
cairosvg.svg2png(bytestring=data.encode(),write_to=str(P/'05-blindspot-overview.png'),output_width=1920,output_height=1080)
