import { ArrowRight, ArrowUpRight, Bot, Box, Camera, Cpu, Crosshair, FileCheck2, Fingerprint, GitBranch, Hand, KeyRound, LayoutDashboard, LockKeyhole, Network, OctagonX, Radar, Radio, ScanSearch, Server, ShieldAlert, ShieldCheck, Wifi, Workflow } from 'lucide-react'
import { MotionConfig, motion, useMotionValueEvent, useReducedMotion, useScroll, useSpring, useTransform } from 'motion/react'
import { useRef, useState, type MouseEvent, type ReactNode } from 'react'
import { Tilt, useRevealProgress, wordVariants, WordReveal } from './effects'
import { Scene, ScrollCue, ShieldArt, useHorizontalScroll, WorkspaceArt } from './visuals'
import espressif from './logos/espressif.svg'
import nvidia from './logos/nvidia.svg'
import react from './logos/react.svg'
import spacetimedb from './logos/spacetimedb.svg'
import three from './logos/threedotjs.svg'
import './landing.css'

const CONSOLE = '#overview'
const REPO = 'https://github.com/ch1kim0n1/hackutd26'
const EASE = [.16, 1, .3, 1] as const
const show = (name: string) => `${import.meta.env.BASE_URL}showcase/${name}`

const stats: { label: string; final: string; render: (p: number) => string }[] = [
  { label: 'Connected workspaces', final: '06', render: p => String(Math.round(6 * p)).padStart(2, '0') },
  { label: 'Workflow stages', final: '08', render: p => String(Math.round(8 * p)).padStart(2, '0') },
  { label: 'Physical Pi stations', final: '02', render: p => String(Math.round(2 * p)).padStart(2, '0') },
  { label: 'Sponsor challenges', final: '03', render: p => String(Math.round(3 * p)).padStart(2, '0') },
]

const pipeline = [
  { icon: Radio, name: 'Sense', line: 'Sensors catch the unusual.' },
  { icon: ScanSearch, name: 'Detect', line: 'Signals correlate into an incident.' },
  { icon: Bot, name: 'Analyze', line: 'Nemotron weighs the evidence.' },
  { icon: Crosshair, name: 'Investigate', line: 'The rover goes to look.' },
  { icon: FileCheck2, name: 'Report', line: 'Findings land. Humans decide.' },
]

const workspaces = [
  { id: 'overview', icon: LayoutDashboard, name: 'Command Overview' },
  { id: 'twin', icon: Box, name: 'Digital Twin' },
  { id: 'network', icon: Network, name: 'Network Intelligence' },
  { id: 'incidents', icon: ShieldAlert, name: 'Incident Center' },
  { id: 'rover', icon: Crosshair, name: 'Rover Operations' },
  { id: 'intelligence', icon: Bot, name: 'Nemotron Intelligence' },
]

const hardware = [
  { icon: Crosshair, name: 'PiCar-X rover', line: 'Autonomous inspection on wheels. Camera, ultrasonic and AprilTag targeting. Dispatched only after human approval.' },
  { icon: Radar, name: 'MS200 LiDAR', line: 'Real 360° scans feed the occupancy grid behind the 3D digital twin.' },
  { icon: Server, name: '2 Raspberry Pi stations', line: 'Actual server telemetry: CPU, services, network flows. Signed and streamed over TLS MQTT.' },
  { icon: Wifi, name: 'ESP32 wireless sensors', line: 'Wi-Fi, BLE and cabinet-tamper signals at the edge, on ESP-IDF firmware.' },
]

const defence = [
  { icon: Fingerprint, name: 'Signed ingest', line: 'Every packet is HMAC-SHA256 signed, schema-checked and replay-protected. Bad data never becomes an incident.' },
  { icon: LockKeyhole, name: 'Isolated by design', line: 'Read-only live mode. Per-device MQTT identities, TLS, and no inbound control path from the dashboard.' },
  { icon: KeyRound, name: 'Scoped agent tools', line: 'Nemotron reads stored evidence through narrow tools. No shell. No motor control. No self-approval.' },
  { icon: GitBranch, name: 'Verified outcomes', line: 'Hashed artifacts, provenance labels and reassessment close the loop on every investigation.' },
]

const guardrails = [
  { icon: Hand, name: 'Human approval', line: 'You sign off on every response.' },
  { icon: OctagonX, name: 'Independent E-stop', line: 'Halts the rover instantly.' },
  { icon: Workflow, name: 'No AI at the wheel', line: 'The agent proposes. Policy decides.' },
  { icon: GitBranch, name: 'Full evidence trail', line: 'Every conclusion is traceable.' },
]

const stack: { name: string; logo?: string }[] = [
  { name: 'NVIDIA Nemotron', logo: nvidia },
  { name: 'SpacetimeDB', logo: spacetimedb },
  { name: 'React', logo: react },
  { name: 'Three.js', logo: three },
  { name: 'ESP32', logo: espressif },
  { name: 'ROS 2' },
  { name: 'FastAPI' },
  { name: 'MQTT + TLS' },
]

const grid = { hidden: {}, show: { transition: { staggerChildren: .09 } } }
const tile = {
  hidden: { opacity: 0, y: 40 },
  show: { opacity: 1, y: 0, transition: { duration: .7, ease: EASE } },
}
const slideIn = {
  hidden: { opacity: 0, y: 24 },
  show: { opacity: 1, y: 0, transition: { duration: .6, ease: EASE } },
}
const inView = { initial: 'hidden', whileInView: 'show', viewport: { once: true, margin: '-80px' } } as const

// Section links scroll in place: any hash change on `/` hands over to the dashboard.
function Jump({ to, className, children }: { to: string; className?: string; children: ReactNode }) {
  const go = (event: MouseEvent) => { event.preventDefault(); document.getElementById(to)?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' }) }
  return <a href={`#${to}`} className={className} onClick={go}>{children}</a>
}

function Heading({ eyebrow, title }: { eyebrow: string; title: string }) {
  return <header className="lp-head">
    <p className="lp-eyebrow">{eyebrow}</p>
    <WordReveal text={title} />
  </header>
}

function Hero() {
  const ref = useRef<HTMLDivElement>(null)
  const reduced = useReducedMotion()
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start start', 'end start'] })
  const copyY = useTransform(scrollYProgress, [0, 1], [0, -100])
  const copyOpacity = useTransform(scrollYProgress, [0, .65], [1, 0])
  const mapY = useTransform(scrollYProgress, [0, 1], [0, 60])
  const mapOpacity = useTransform(scrollYProgress, [.3, .9], [1, 0])
  return <div ref={ref} className="lp-hero-wrap">
    <section className="lp-hero" aria-labelledby="lp-title">
      <motion.div className="lp-hero-copy" style={reduced ? undefined : { y: copyY, opacity: copyOpacity }}>
        <motion.h1 id="lp-title" initial="hidden" animate="show" transition={{ staggerChildren: .08, delayChildren: .1 }}>
          {[['Security', 'that'], ['moves', 'into', 'the']].map(line => <span key={line[0]} className="lp-line">{line.map(word => <span key={word} className="lp-word"><motion.span variants={wordVariants}>{word}</motion.span></span>)}</span>)}
          <span className="lp-line"><span className="lp-word"><motion.em variants={wordVariants} className="lp-accent-word">blind spot.</motion.em></span></span>
        </motion.h1>
        <motion.p className="lp-hero-lead" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .7, delay: .6, ease: EASE }}>An autonomous rover, live sensors and a Nemotron AI analyst turn alerts into evidence. You stay in control.</motion.p>
        <motion.div className="lp-actions" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .7, delay: .75, ease: EASE }}>
          <a className="lp-btn" href={CONSOLE}>Launch Phantom Command <ArrowRight size={18} /></a>
          <Jump to="how" className="lp-textlink">How it works</Jump>
        </motion.div>
      </motion.div>
      <motion.div className="lp-hero-visual" style={reduced ? undefined : { y: mapY, opacity: mapOpacity }}>
        <motion.div initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .9, delay: .15, ease: EASE }}>
          <Tilt className="lp-tilt">
            <div className="lp-photo lp-hero-photo"><img src={show("hero-concept.webp")} alt="BlindSpot rover patrolling a data center aisle between server racks" /></div>
          </Tilt>
        </motion.div>
      </motion.div>
    </section>
    <motion.div style={reduced ? undefined : { opacity: copyOpacity }}><ScrollCue /></motion.div>
  </div>
}

function Stats() {
  const [ref, progress] = useRevealProgress()
  return <motion.ul ref={ref} className="lp-stats" aria-label="At a glance" variants={grid} {...inView}>
    {stats.map(s => <motion.li key={s.label} variants={tile}><strong><span className="lp-sr">{s.final}</span><span aria-hidden="true">{s.render(progress)}</span></strong><span>{s.label}</span></motion.li>)}
  </motion.ul>
}

/** Problem → solution: the two-slide judge pitch, side by side. */
function ProblemSolution() {
  return <section id="problem" className="lp-section" aria-labelledby="problem-title">
    <Heading eyebrow="Problem → solution" title="Alerts are cheap. Evidence is not." />
    <div className="lp-ps">
      <motion.article className="lp-ps-card is-problem" variants={slideIn} {...inView}>
        <div className="lp-ps-photo"><img src={show("stock-datacenter.jpg")} alt="Data center aisle with rows of server racks" loading="lazy" /><span className="lp-ps-tag">The problem</span></div>
        <div className="lp-ps-body">
          <h3>A missed warning becomes an outage.</h3>
          <p>Behind every AI model, stream and cloud app is a data center running around the clock. Logs, network flows and the physical rack live in separate tools, so responders reconstruct the story by hand. The wrong information at the wrong time turns a small issue into a major disruption.</p>
        </div>
      </motion.article>
      <motion.article className="lp-ps-card is-solution" variants={slideIn} {...inView}>
        <div className="lp-ps-photo"><img src={show("incident-response-concept.webp")} alt="BlindSpot incident response concept: from anomaly to verified evidence" loading="lazy" /><span className="lp-ps-tag">Our answer</span></div>
        <div className="lp-ps-body">
          <h3>BlindSpot investigates before it escalates.</h3>
          <p>Signed telemetry becomes a correlated incident. Nemotron investigates the stored evidence. A human approves a bounded rover inspection. Hashed findings come back and the agent reassesses. One loop, from blind spot to informed response.</p>
        </div>
      </motion.article>
    </div>
  </section>
}

/** Pinned while you scroll through it: the line fills and each step lights up in turn. */
function Pipeline() {
  const ref = useRef<HTMLElement>(null)
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start start', 'end end'] })
  const fill = useSpring(scrollYProgress, { stiffness: 140, damping: 26, restDelta: .001 })
  const [active, setActive] = useState(0)
  const last = pipeline.length - 1
  useMotionValueEvent(scrollYProgress, 'change', v => setActive(Math.min(last, Math.max(0, Math.floor(v * last + .2)))))
  const step = pipeline[active]
  return <section id="how" ref={ref} className="lp-story" aria-labelledby="how-title" style={{ height: `${pipeline.length * 60 + 60}vh` }}>
    <div className="lp-story-sticky">
      <header className="lp-head">
        <p className="lp-eyebrow">How it works</p>
        <h2 id="how-title">Signal to verdict.</h2>
      </header>
      <div className="lp-story-track">
        <div className="lp-story-line"><motion.div className="lp-story-fill" style={{ scaleX: fill }} /></div>
        {pipeline.map((s, i) => <div key={s.name} className={`lp-story-step ${i <= active ? 'is-done' : ''} ${i === active ? 'is-active' : ''}`}>
          <span className="lp-story-icon"><s.icon size={26} strokeWidth={1.6} /></span><b>{s.name}</b>
        </div>)}
      </div>
      <p className="lp-story-caption" aria-live="polite">{step.line}</p>
    </div>
  </section>
}

function Hardware() {
  return <section id="hardware" className="lp-section" aria-label="Hardware">
    <Heading eyebrow="Hardware" title="Real metal. Real signals." />
    <Scene className="lp-hw-layout">
      <div className="lp-photo lp-hw-photo"><img src={show("hardware-concept.webp")} alt="PiCar-X rover with LiDAR turret, camera and three wireless sensor pucks" loading="lazy" /></div>
      <motion.div className="lp-hw-grid" variants={grid} {...inView}>
        {hardware.map(h => <motion.div key={h.name} className="lp-hw-card" variants={tile}>
          <span className="lp-guard-icon"><h.icon size={26} strokeWidth={1.6} /></span><h3>{h.name}</h3><p>{h.line}</p>
        </motion.div>)}
      </motion.div>
    </Scene>
    <Scene><div className="lp-photo lp-wide-photo"><img src={show("stock-circuit.jpg")} alt="Macro photograph of a printed circuit board" loading="lazy" /><span className="lp-photo-caption"><Cpu size={18} /> Raspberry Pi · ESP32 · ROS 2 · MS200 LiDAR</span></div></Scene>
  </section>
}

/** Workspace cards travel sideways while the section is pinned. */
function Gallery() {
  const { section, track, x, progress, height } = useHorizontalScroll()
  return <section id="workspaces" ref={section} className="lp-gallery" aria-label="Workspaces" style={{ height: height === null ? undefined : `calc(100vh + ${height}px)` }}>
    <div className="lp-gallery-sticky">
      <div className="lp-gallery-head"><Heading eyebrow="Phantom Command" title="Six views. One operation." /></div>
      <motion.div ref={track} className="lp-gallery-track" style={{ x }}>
        {workspaces.map((w, i) => <motion.a key={w.id} href={`#${w.id}`} className="lp-wcard" variants={tile} {...inView} transition={{ delay: i * .06 }}>
          <div className="lp-wcard-art"><WorkspaceArt id={w.id} /></div>
          <div className="lp-wcard-foot"><span className="lp-card-icon"><w.icon size={22} strokeWidth={1.6} /></span><h3>{w.name}</h3><ArrowUpRight size={22} className="lp-card-arrow" /></div>
        </motion.a>)}
      </motion.div>
      <div className="lp-gallery-progress" aria-hidden="true"><motion.i style={{ scaleX: progress }} /></div>
    </div>
  </section>
}

function Architecture() {
  return <section id="software" className="lp-section" aria-label="Software architecture">
    <Heading eyebrow="Software" title="One pipeline. Every signal connected." />
    <Scene><div className="lp-photo lp-diagram"><img src={show("06_blindspot_architecture.webp")} alt="Architecture: physical sensors through MQTT gateway, SpacetimeDB, AI investigation, human approval and mission bridge to Phantom Command" loading="lazy" /></div></Scene>
    <motion.ul className="lp-stack" variants={grid} {...inView}>{stack.map(s => <motion.li key={s.name} variants={slideIn}>
      {s.logo && <span className="lp-logo" style={{ '--logo': `url(${JSON.stringify(s.logo)})` } as never} />}{s.name}
    </motion.li>)}</motion.ul>
  </section>
}

function CyberDefence() {
  return <>
    <section id="defence" className="lp-section" aria-label="Cyber defence">
      <Heading eyebrow="Cyber defence" title="Built assuming the attacker is inside." />
      <motion.div className="lp-defence-grid" variants={grid} {...inView}>
        {defence.map(d => <motion.div key={d.name} className="lp-defence-card" variants={tile}>
          <span className="lp-guard-icon"><d.icon size={26} strokeWidth={1.6} /></span><h3>{d.name}</h3><p>{d.line}</p>
        </motion.div>)}
      </motion.div>
      <Scene><div className="lp-photo lp-diagram"><img src={show("04-evidence-graph.webp")} alt="Evidence provenance graph: observed, derived, inferred, approved and verified states stay distinct" loading="lazy" /></div></Scene>
    </section>
    <section id="guardrails" className="lp-section" aria-label="Guardrails">
      <Scene className="lp-guard-layout">
        <ShieldArt />
        <div>
          <Heading eyebrow="Guardrails" title="Autonomous. Accountable." />
          <motion.div className="lp-guardrails" variants={grid} {...inView}>{guardrails.map(g => <motion.div key={g.name} className="lp-guardrail" variants={slideIn}>
            <span className="lp-guard-icon"><g.icon size={24} strokeWidth={1.6} /></span><div><h3>{g.name}</h3><p>{g.line}</p></div>
          </motion.div>)}</motion.div>
        </div>
      </Scene>
    </section>
  </>
}

const sponsors = [
  {
    id: 'nmc2', name: 'NMC²', tag: 'Mission: Keep the World Running', image: show("stock-datacenter.jpg"), alt: 'Server racks in a data center',
    hook: 'A command center that keeps data center teams one step ahead.',
    points: [
      'Live server health from real Raspberry Pi stations, not a canned dashboard.',
      'A 3D digital twin of the facility, so responders see where the problem is.',
      'A rover that physically inspects the rack, closing the gap between alert and reality.',
      'Fewer missed warnings, clearer handoffs. Every incident carries its own evidence.',
    ],
  },
  {
    id: 'winstead', name: 'Winstead', tag: 'Cyber Incident Response Dashboard', image: show("stock-cables.jpg"), alt: 'Network cabling in a server rack',
    hook: 'All five required components, working as one system.',
    points: [
      'Secure and isolated. Signed ingest, read-only live mode, no inbound control path.',
      'Access control. Commander approvals sit outside the model, enforced by policy.',
      'Incident documentation. Evidence, timelines and hashed artifacts on every case.',
      'Scope definitions. Registered targets and bounded missions only.',
      'Real-time communications. Live subscriptions, approvals inbox, instant E-stop.',
    ],
  },
  {
    id: 'nvidia', name: 'NVIDIA', tag: 'Use Nemotron Beyond a Chatbot', image: show("stock-circuit.jpg"), alt: 'Close-up of circuit board components',
    hook: 'An agent that plans and executes. No prompt required.',
    points: [
      'Multi-step workflows: observe, reason, propose, inspect, reassess. Event-driven, not prompt-driven.',
      'Tool integration: scoped evidence tools, MQTT telemetry, mission bridge and external APIs.',
      'Real-world applicability: physical rover dispatch with human authorization and verified results.',
      'Honest autonomy: Nemotron cites stored evidence, and a deterministic provider keeps demos repeatable.',
    ],
  },
]

function Sponsors() {
  return <section id="sponsors" className="lp-section" aria-label="Sponsor challenges">
    <Heading eyebrow="Sponsor challenges" title="Why we fit each track." />
    <div className="lp-sponsors">
      {sponsors.map(s => <motion.article key={s.id} id={s.id} className={`lp-sponsor is-${s.id}`} variants={slideIn} {...inView}>
        <div className="lp-sponsor-photo"><img src={s.image} alt={s.alt} loading="lazy" /><div className="lp-sponsor-title"><span className="lp-sponsor-tag">{s.tag}</span><h3>{s.name}</h3></div></div>
        <div className="lp-sponsor-body">
          <p className="lp-sponsor-hook">{s.hook}</p>
          <ul>{s.points.map(p => <li key={p}><ShieldCheck size={22} strokeWidth={1.8} /><span>{p}</span></li>)}</ul>
        </div>
      </motion.article>)}
    </div>
  </section>
}

export default function Landing() {
  const { scrollYProgress } = useScroll()
  const progress = useSpring(scrollYProgress, { stiffness: 200, damping: 30, restDelta: .001 })

  return <MotionConfig reducedMotion="user"><div className="lp">
    <motion.div className="lp-progress" style={{ scaleX: progress }} aria-hidden="true" />

    <main>
      <Hero />
      <Scene><Stats /></Scene>
      <ProblemSolution />
      <Pipeline />
      <Hardware />
      <Gallery />
      <Architecture />
      <CyberDefence />
      <Sponsors />

      <section className="lp-cta" aria-label="Get started">
        <WordReveal text="See it in action." />
        <div className="lp-actions">
          <a className="lp-btn" href={CONSOLE}>Launch Phantom Command <ArrowRight size={18} /></a>
          <a className="lp-textlink" href={REPO} target="_blank" rel="noreferrer">Source on GitHub <ArrowUpRight size={16} /></a>
        </div>
      </section>
    </main>

    <footer className="lp-footer"><span>BlindSpot · HackUTD 2026</span><span><Camera size={15} /> Concept illustrations + Unsplash photography · demo data simulated</span></footer>
  </div></MotionConfig>
}
