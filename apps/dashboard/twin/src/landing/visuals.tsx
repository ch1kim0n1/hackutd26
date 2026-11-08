import { motion, useMotionValue, useReducedMotion, useScroll, useTransform, type MotionValue } from 'motion/react'
import { useEffect, useRef, useState, type ReactNode } from 'react'

/** Wraps a block so it scales/fades in as it enters the viewport and settles back as it leaves. */
export function Scene({ children, className }: { children: ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const reduced = useReducedMotion()
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start end', 'end start'] })
  const scale = useTransform(scrollYProgress, [0, .3, .8, 1], [.9, 1, 1, .95])
  const opacity = useTransform(scrollYProgress, [0, .22, .85, 1], [0, 1, 1, .35])
  const y = useTransform(scrollYProgress, [0, .3], [90, 0])
  return <motion.div ref={ref} className={className} style={reduced ? undefined : { scale, opacity, y }}>{children}</motion.div>
}

/** Two rows of huge outlined words sliding in opposite directions as the page scrolls. */
export function MarqueeBand({ words }: { words: string[] }) {
  const ref = useRef<HTMLDivElement>(null)
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start end', 'end start'] })
  const left = useTransform(scrollYProgress, [0, 1], ['0%', '-30%'])
  const right = useTransform(scrollYProgress, [0, 1], ['-30%', '0%'])
  const row = (x: MotionValue<string>, accent: number) => <motion.div className="lp-band-row" style={{ x }}>
    {[...words, ...words, ...words].map((w, i) => <span key={i} className={i % words.length === accent ? 'is-fill' : ''}>{w}<i>◆</i></span>)}
  </motion.div>
  return <div ref={ref} className="lp-band" aria-hidden="true">{row(left, 2)}{row(right, 4)}</div>
}

export function ScrollCue() {
  return <div className="lp-cue" aria-hidden="true"><span className="lp-cue-mouse"><i /></span>Scroll</div>
}

/** Big shield whose outline and check draw in as the section scrolls past, wrapped in rotating rings. */
export function ShieldArt() {
  const ref = useRef<HTMLDivElement>(null)
  const reduced = useReducedMotion()
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start end', 'center center'] })
  const draw = useTransform(scrollYProgress, [0, .85], [0, 1])
  const check = useTransform(scrollYProgress, [.6, 1], [0, 1])
  const fill = useTransform(scrollYProgress, [.7, 1], [0, 1])
  return <div ref={ref} className="lp-shield" aria-hidden="true">
    <svg viewBox="0 0 400 400">
      <defs>
        <radialGradient id="lp-shield-glow"><stop offset="0" stopColor="#22c55e" stopOpacity=".28" /><stop offset="1" stopColor="#22c55e" stopOpacity="0" /></radialGradient>
        <linearGradient id="lp-shield-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#22c55e" stopOpacity=".22" /><stop offset="1" stopColor="#10b981" stopOpacity=".04" /></linearGradient>
      </defs>
      <circle cx="200" cy="200" r="190" fill="url(#lp-shield-glow)" />
      <g className="lp-shield-ring is-a"><circle cx="200" cy="200" r="170" /></g>
      <g className="lp-shield-ring is-b"><circle cx="200" cy="200" r="140" /></g>
      <g className="lp-shield-ring is-c"><circle cx="200" cy="200" r="112" /></g>
      <g className="lp-shield-orbit is-a"><circle cx="200" cy="30" r="5" /></g>
      <g className="lp-shield-orbit is-b"><circle cx="200" cy="60" r="4" /><circle cx="200" cy="340" r="4" /></g>
      <motion.path d="M200 108 268 134v58c0 44-30 74-68 92-38-18-68-48-68-92v-58Z" fill="url(#lp-shield-fill)" style={reduced ? undefined : { opacity: fill }} />
      <motion.path d="M200 108 268 134v58c0 44-30 74-68 92-38-18-68-48-68-92v-58Z" className="lp-shield-line" style={reduced ? undefined : { pathLength: draw }} />
      <motion.path d="m170 196 22 22 40-44" className="lp-shield-check" style={reduced ? undefined : { pathLength: check }} />
    </svg>
  </div>
}

/** Small animated preview art for each dashboard workspace card. */
export function WorkspaceArt({ id }: { id: string }) {
  const art: Record<string, ReactNode> = {
    overview: <>
      {[0, 1, 2, 3, 4, 5, 6].map(i => <rect key={i} x={20 + i * 34} y={40} width="22" height="90" rx="4" className="lp-art-bar" style={{ animationDelay: `${i * .18}s` }} />)}
      <path d="M14 70 C60 30 90 90 130 60 S200 20 250 50" className="lp-art-line" />
    </>,
    twin: <>
      <g className="lp-art-iso">
        <path d="M130 30 210 72 130 114 50 72Z" className="lp-art-face" />
        <path d="M50 72v34l80 42v-34ZM210 72v34l-80 42v-34Z" className="lp-art-face is-side" />
        {[0, 1, 2].map(i => <path key={i} d={`M${70 + i * 20} ${82 + i * 10} L${150 + i * 20} ${40 + i * 10}`} className="lp-art-grid" />)}
      </g>
      <circle r="5" className="lp-art-dot"><animateMotion dur="5s" repeatCount="indefinite" path="M90 72 L130 52 L170 72 L130 92Z" /></circle>
    </>,
    network: <>
      {[[40, 50, 120, 30], [120, 30, 200, 70], [40, 50, 90, 120], [90, 120, 200, 70], [120, 30, 160, 125], [160, 125, 230, 120], [200, 70, 230, 120]].map(([a, b, c, d], i) => <line key={i} x1={a} y1={b} x2={c} y2={d} className="lp-art-edge" />)}
      {[[40, 50], [120, 30], [200, 70], [90, 120], [160, 125], [230, 120]].map(([x, y], i) => <circle key={i} cx={x} cy={y} r={i === 2 ? 8 : 6} className={`lp-art-node ${i === 2 ? 'is-threat' : ''}`} style={{ animationDelay: `${i * .3}s` }} />)}
    </>,
    incidents: <>
      <line x1="40" y1="20" x2="40" y2="130" className="lp-art-edge" />
      {[30, 62, 94, 120].map((y, i) => <g key={y}><circle cx="40" cy={y} r="6" className={`lp-art-node ${i === 1 ? 'is-threat' : ''}`} style={{ animationDelay: `${i * .4}s` }} /><rect x="60" y={y - 6} width={140 - i * 22} height="12" rx="6" className="lp-art-pill" style={{ animationDelay: `${i * .25}s` }} /></g>)}
    </>,
    rover: <>
      {[24, 46, 68].map(r => <circle key={r} cx="130" cy="75" r={r} className="lp-art-ring" />)}
      <path d="M130 75 L198 75 A68 68 0 0 0 178 27Z" className="lp-art-sweep" />
      {[[160, 50], [96, 98], [176, 104], [84, 54], [150, 120]].map(([x, y], i) => <circle key={i} cx={x} cy={y} r="3" className="lp-art-blip" style={{ animationDelay: `${i * .45}s` }} />)}
      <circle cx="130" cy="75" r="6" className="lp-art-dot" />
    </>,
    intelligence: <>
      {Array.from({ length: 26 }, (_, i) => <rect key={i} x={14 + i * 9} y={40} width="5" height="70" rx="2.5" className="lp-art-wave" style={{ animationDelay: `${(i % 9) * .11}s` }} />)}
    </>,
  }
  return <svg viewBox="0 0 260 150" className="lp-art" aria-hidden="true">{art[id]}</svg>
}

/** Pinned section that converts vertical scroll into horizontal travel of its track. */
export function useHorizontalScroll() {
  const section = useRef<HTMLElement>(null), track = useRef<HTMLDivElement>(null)
  const distance = useMotionValue(0)
  const [height, setHeight] = useState<number | null>(null)
  useEffect(() => {
    const el = track.current
    if (!el) return
    const measure = () => { const d = Math.max(0, el.scrollWidth - window.innerWidth); distance.set(d); setHeight(d) }
    measure()
    const sizer = new ResizeObserver(measure)
    sizer.observe(el)
    window.addEventListener('resize', measure)
    return () => { sizer.disconnect(); window.removeEventListener('resize', measure) }
  }, [distance])
  const { scrollYProgress } = useScroll({ target: section, offset: ['start start', 'end end'] })
  const x = useTransform(() => -scrollYProgress.get() * distance.get())
  return { section, track, x, progress: scrollYProgress, height }
}
