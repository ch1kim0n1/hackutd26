import { ArrowRight, ArrowUpRight, Bot, Box, Crosshair, FileCheck2, GitBranch, Hand, LayoutDashboard, Network, OctagonX, Radar, Radio, ScanSearch, Shield, ShieldAlert, Workflow } from 'lucide-react'
import { AnimatePresence, MotionConfig, motion, useMotionValueEvent, useReducedMotion, useScroll, useSpring, useTransform } from 'motion/react'
import { useEffect, useRef, useState, type MouseEvent, type ReactNode } from 'react'
import { Scramble, SignalMesh, spot, Tilt, useRevealProgress, wordVariants, WordReveal } from './effects'
import './landing.css'

const CONSOLE = '#overview'
const REPO = 'https://github.com/ch1kim0n1/hackutd26'
const EASE = [.16, 1, .3, 1] as const

const stats: { label: string; final: string; render: (p: number) => string }[] = [
  { label: 'Live workspaces', final: '06', render: p => String(Math.round(6 * p)).padStart(2, '0') },
  { label: 'Devices tracked', final: '32', render: p => String(Math.round(32 * p)) },
  { label: 'Digital twin', final: '24×18 m', render: p => `${Math.round(24 * p)}×${Math.round(18 * p)} m` },
  { label: 'Setup required', final: '0', render: p => String(Math.round(12 * (1 - p))) },
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

const guardrails = [
  { icon: Hand, name: 'Human approval', line: 'You sign off on every response.' },
  { icon: OctagonX, name: 'Independent E-stop', line: 'Halts the rover instantly.' },
  { icon: Workflow, name: 'No AI at the wheel', line: 'The agent proposes. Policy decides.' },
  { icon: GitBranch, name: 'Full evidence trail', line: 'Every conclusion is traceable.' },
]

const stack = ['NVIDIA Nemotron', 'SpacetimeDB', 'React', 'Three.js', 'ROS 2', 'ESP32']

const grid = { hidden: {}, show: { transition: { staggerChildren: .09 } } }
const tile = {
  hidden: { opacity: 0, y: 60, scale: .94, rotateX: 14 },
  show: { opacity: 1, y: 0, scale: 1, rotateX: 0, transition: { duration: .9, ease: EASE } },
}
const inView = { initial: 'hidden', whileInView: 'show', viewport: { once: true, margin: '-80px' } } as const

// Section links scroll in place: any hash change on `/` hands over to the dashboard.
function Jump({ to, className, children }: { to: string; className?: string; children: ReactNode }) {
  const go = (event: MouseEvent) => { event.preventDefault(); document.getElementById(to)?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' }) }
  return <a href={`#${to}`} className={className} onClick={go}>{children}</a>
}

function Heading({ eyebrow, title, center }: { eyebrow: string; title: string; center?: boolean }) {
  return <header className={`lp-head ${center ? 'is-center' : ''}`}>
    <p className="lp-eyebrow"><span className="lp-prompt">&gt;</span><Scramble text={eyebrow} /><span className="lp-caret" /></p>
    <WordReveal text={title} />
  </header>
}

/** Stylised, purely decorative facility map: 24×18 m at 20 px per metre. */
function FacilityMap() {
  const racks = Array.from({ length: 12 }, (_, i) => ({ x: 270 + (i % 4) * 44, y: 54 + Math.floor(i / 4) * 62 }))
  const aps = [[60, 60], [200, 70], [430, 300], [110, 290]]
  const reduced = useReducedMotion()
  const route = 'M80 300H165V167H352'
  return <div className="lp-map" aria-hidden="true">
    <div className="lp-map-bar"><span><i className="lp-dot is-live" /> FACILITY 01</span><span className="lp-rec"><i /> LIVE TWIN</span></div>
    <div className="lp-map-stage">
      <svg viewBox="0 0 480 360" className="lp-map-svg">
        <defs>
          <pattern id="lp-grid" width="20" height="20" patternUnits="userSpaceOnUse"><path d="M20 0H0V20" fill="none" stroke="currentColor" strokeWidth=".5" /></pattern>
          <radialGradient id="lp-threat-glow"><stop offset="0" stopColor="#ef4444" stopOpacity=".5" /><stop offset="1" stopColor="#ef4444" stopOpacity="0" /></radialGradient>
          <radialGradient id="lp-cone"><stop offset="0" stopColor="#eab308" stopOpacity=".35" /><stop offset="1" stopColor="#eab308" stopOpacity="0" /></radialGradient>
        </defs>
        <rect width="480" height="360" fill="url(#lp-grid)" className="lp-map-grid" />
        <rect x="236" y="30" width="224" height="204" className="lp-zone is-threat" />
        <path d="M20 20H460V340H20Z M236 20V150 M236 185V234H300 M330 234H460 M20 234H150 M180 234H236 M120 234V340" className="lp-walls" />
        {racks.map((r, i) => <rect key={i} x={r.x} y={r.y} width="30" height="40" rx="2" className={`lp-rack ${i === 6 ? 'is-hot' : ''}`} style={{ animationDelay: `${(i * 0.37) % 2}s` }} />)}
        {aps.map(([x, y], i) => <g key={i}><circle cx={x} cy={y} r="14" className="lp-ap-ring" style={{ animationDelay: `${i * .7}s` }} /><circle cx={x} cy={y} r="14" className="lp-ap-ring" style={{ animationDelay: `${i * .7 + 1.5}s` }} /><circle cx={x} cy={y} r="3" className="lp-ap" /></g>)}
        <circle cx="373" cy="137" r="50" fill="url(#lp-threat-glow)" className="lp-threat-glow" />
        <path d={route} className="lp-route-base" />
        <path d={route} className="lp-route" />
        <g className="lp-threat"><circle cx="373" cy="137" r="5" /><circle cx="373" cy="137" r="12" className="lp-threat-ring" /><path d="M373 118v7M373 149v7M354 137h7M385 137h7" /></g>
        <g transform="translate(318 84)" className="lp-callout-group"><rect width="110" height="24" rx="4" className="lp-callout" /><text x="55" y="16.5" textAnchor="middle" className="lp-callout-text">THREAT</text></g>
        <g className="lp-rover" transform={reduced ? 'translate(352 167)' : undefined}>
          <path d="M0 0L34 -18A38 38 0 0 1 34 18Z" fill="url(#lp-cone)" className="lp-rover-cone" />
          <circle r="12" className="lp-rover-ring" /><circle r="5" className="lp-rover-core" />
          {!reduced && <animateMotion dur="7s" repeatCount="indefinite" path={route} rotate="auto" keyPoints="0;1;1" keyTimes="0;.7;1" calcMode="linear" />}
        </g>
      </svg>
      <div className="lp-sweep" />
      <div className="lp-scanlines" />
      <span className="lp-hud is-tl" /><span className="lp-hud is-tr" /><span className="lp-hud is-bl" /><span className="lp-hud is-br" />
    </div>
  </div>
}

function Hero() {
  const ref = useRef<HTMLDivElement>(null)
  const reduced = useReducedMotion()
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start start', 'end start'] })
  const copyY = useTransform(scrollYProgress, [0, 1], [0, -140])
  const copyOpacity = useTransform(scrollYProgress, [0, .65], [1, 0])
  const mapY = useTransform(scrollYProgress, [0, 1], [0, 90])
  const mapScale = useTransform(scrollYProgress, [0, 1], [1, .88])
  const mapOpacity = useTransform(scrollYProgress, [.3, .9], [1, 0])
  return <div ref={ref} className="lp-hero-wrap">
    <SignalMesh className="lp-mesh" />
    <section className="lp-hero" aria-labelledby="lp-title">
      <motion.div className="lp-hero-copy" style={reduced ? undefined : { y: copyY, opacity: copyOpacity }}>
        <motion.p className="lp-pill" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .6, ease: EASE }}><span className="lp-dot is-live" /><Scramble text="HackUTD 2026" speed={40} /></motion.p>
        <motion.h1 id="lp-title" initial="hidden" animate="show" transition={{ staggerChildren: .08, delayChildren: .15 }}>
          {[['Security', 'that'], ['moves', 'into', 'the']].map(line => <span key={line[0]} className="lp-line">{line.map(word => <span key={word} className="lp-word"><motion.span variants={wordVariants}>{word}</motion.span></span>)}</span>)}
          <span className="lp-line"><span className="lp-word"><motion.em variants={wordVariants} className="lp-glitch" data-text="blind spot.">blind spot.</motion.em></span></span>
        </motion.h1>
        <motion.p className="lp-hero-lead" initial={{ opacity: 0, y: 16, filter: 'blur(6px)' }} animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }} transition={{ duration: .8, delay: .75, ease: EASE }}>An autonomous rover, live sensors and an AI analyst. You stay in control.</motion.p>
        <motion.div className="lp-actions" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .8, delay: .9, ease: EASE }}>
          <a className="lp-btn is-pulse" href={CONSOLE}><Radar size={18} /> Launch Phantom Command <ArrowRight size={18} /></a>
          <Jump to="how" className="lp-btn is-ghost">How it works</Jump>
        </motion.div>
      </motion.div>
      <motion.div className="lp-hero-visual" style={reduced ? undefined : { y: mapY, scale: mapScale, opacity: mapOpacity }}>
        <motion.div initial={{ opacity: 0, y: 40, scale: .94, rotateX: 18 }} animate={{ opacity: 1, y: 0, scale: 1, rotateX: 0 }} transition={{ duration: 1.2, delay: .2, ease: EASE }} style={{ transformPerspective: 1400 }}>
          <Tilt className="lp-tilt">
            <FacilityMap />
            <div className="lp-glare" aria-hidden="true" />
            <div className="lp-float is-approval"><span className="lp-float-icon"><Hand size={18} /></span><span><b>Approve isolation?</b><small>Waiting on you</small></span></div>
            <div className="lp-float is-agent"><span className="lp-float-icon is-amber"><Bot size={18} /></span><span><b>Agent</b><small>Investigating…</small></span></div>
          </Tilt>
        </motion.div>
      </motion.div>
    </section>
  </div>
}

function Stats() {
  const [ref, progress] = useRevealProgress()
  return <motion.ul ref={ref} className="lp-stats" aria-label="At a glance" variants={grid} {...inView}>
    {stats.map(s => <motion.li key={s.label} variants={tile} className="lp-glow" onPointerMove={spot}><strong><span className="lp-sr">{s.final}</span><span aria-hidden="true">{s.render(progress)}</span></strong><span>{s.label}</span></motion.li>)}
  </motion.ul>
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
      <header className="lp-head is-center">
        <p className="lp-eyebrow"><span className="lp-prompt">&gt;</span><Scramble text="how it works" /><span className="lp-caret" /></p>
        <h2 id="how-title">Signal to verdict.</h2>
      </header>
      <div className="lp-story-track">
        <div className="lp-story-line"><motion.div className="lp-story-fill" style={{ scaleX: fill }} /></div>
        {pipeline.map((s, i) => <div key={s.name} className={`lp-story-step ${i <= active ? 'is-done' : ''} ${i === active ? 'is-active' : ''}`}>
          <span className="lp-story-icon"><s.icon size={24} strokeWidth={1.6} /></span><b>{s.name}</b>
        </div>)}
      </div>
      <div className="lp-story-caption" aria-live="polite">
        <AnimatePresence mode="wait" initial={false}>
          <motion.div key={step.name} initial={{ opacity: 0, y: 24, filter: 'blur(8px)' }} animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }} exit={{ opacity: 0, y: -24, filter: 'blur(8px)' }} transition={{ duration: .45, ease: EASE }}>
            <span>0{active + 1} · {step.name}</span><p>{step.line}</p>
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  </section>
}

export default function Landing() {
  const { scrollYProgress } = useScroll()
  const progress = useSpring(scrollYProgress, { stiffness: 200, damping: 30, restDelta: .001 })
  const [scrolled, setScrolled] = useState(false)
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12)
    onScroll(); window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return <MotionConfig reducedMotion="user"><div className="lp">
    <motion.div className="lp-progress" style={{ scaleX: progress }} aria-hidden="true" />
    <div className="lp-backdrop" aria-hidden="true" />
    <header className={`lp-nav ${scrolled ? 'is-scrolled' : ''}`}>
      <div className="lp-nav-inner">
        <a className="lp-brand" href="/" aria-label="BlindSpot home"><span className="lp-brand-mark"><Shield size={24} strokeWidth={1.4} /><i /></span><b>BLINDSPOT</b></a>
        <nav aria-label="Page sections"><Jump to="how">How it works</Jump><Jump to="workspaces">Workspaces</Jump><Jump to="guardrails">Guardrails</Jump></nav>
        <a className="lp-btn is-small" href={CONSOLE}>Launch <ArrowRight size={16} /></a>
      </div>
    </header>

    <main>
      <Hero />
      <Stats />
      <Pipeline />

      <section id="workspaces" className="lp-section" aria-label="Workspaces">
        <Heading eyebrow="phantom command" title="Six views. One operation." />
        <motion.div className="lp-cards" variants={grid} {...inView}>{workspaces.map(w => <motion.a key={w.id} href={`#${w.id}`} className="lp-card lp-glow" onPointerMove={spot} variants={tile}>
          <span className="lp-card-icon"><w.icon size={24} strokeWidth={1.6} /></span>
          <h3>{w.name}</h3>
          <ArrowUpRight size={20} className="lp-card-arrow" />
        </motion.a>)}</motion.div>
      </section>

      <section id="guardrails" className="lp-section" aria-label="Guardrails">
        <Heading eyebrow="guardrails" title="Autonomous. Accountable." />
        <motion.div className="lp-guardrails" variants={grid} {...inView}>{guardrails.map(g => <motion.div key={g.name} className="lp-guardrail lp-glow" onPointerMove={spot} variants={tile}>
          <span className="lp-guard-icon"><g.icon size={24} strokeWidth={1.6} /></span><div><h3>{g.name}</h3><p>{g.line}</p></div>
        </motion.div>)}</motion.div>
      </section>

      <section className="lp-section lp-stack-wrap" aria-label="Built with">
        <motion.ul className="lp-stack" variants={grid} {...inView}>{stack.map(name => <motion.li key={name} variants={{ hidden: { opacity: 0, y: 20, filter: 'blur(6px)' }, show: { opacity: 1, y: 0, filter: 'blur(0px)', transition: { duration: .7, ease: EASE } } }}>{name}</motion.li>)}</motion.ul>
      </section>

      <motion.section className="lp-cta" aria-label="Get started" initial={{ opacity: 0, y: 60, scale: .96 }} whileInView={{ opacity: 1, y: 0, scale: 1 }} viewport={{ once: true, margin: '-80px' }} transition={{ duration: 1, ease: EASE }}>
        <div className="lp-cta-inner">
          <div className="lp-cta-glow" aria-hidden="true" />
          <WordReveal text="See it in action." />
          <div className="lp-actions is-center">
            <a className="lp-btn is-pulse is-large" href={CONSOLE}>Launch Phantom Command <ArrowRight size={20} /></a>
            <a className="lp-btn is-ghost is-large" href={REPO} target="_blank" rel="noreferrer">Source <ArrowUpRight size={18} /></a>
          </div>
        </div>
      </motion.section>
    </main>

    <footer className="lp-footer"><span><span className="lp-dot is-live" /> BlindSpot · HackUTD 2026</span><span>Demo data is simulated.</span></footer>
  </div></MotionConfig>
}
