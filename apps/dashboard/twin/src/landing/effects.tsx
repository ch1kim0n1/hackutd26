import { animate, motion, useInView, useMotionValue, useReducedMotion, useSpring, useTransform } from 'motion/react'
import { useEffect, useRef, useState, type PointerEvent, type ReactNode } from 'react'

export const wordVariants = {
  hidden: { y: '115%', rotate: 3 },
  show: { y: '0%', rotate: 0, transition: { duration: .8, ease: [.16, 1, .3, 1] } },
} as const

/** Heading whose words slide up out of a mask, one after another, when it scrolls into view. */
export function WordReveal({ text, className }: { text: string; className?: string }) {
  return <motion.h2 className={className} aria-label={text} initial="hidden" whileInView="show" viewport={{ once: true, margin: '-80px' }} transition={{ staggerChildren: .07 }}>
    {text.split(' ').map((word, i) => <span key={i} className="lp-word" aria-hidden="true"><motion.span variants={wordVariants}>{word}</motion.span></span>)}
  </motion.h2>
}

const GLYPHS = '!<>-_/\\[]{}=+*^?#%01ABCDEF'
const randomGlyph = () => GLYPHS[Math.floor(Math.random() * GLYPHS.length)]

/** Decodes text from random glyphs when it scrolls into view. Best on monospace text, where widths stay stable. */
export function Scramble({ text, delay = 0, speed = 28 }: { text: string; delay?: number; speed?: number }) {
  const ref = useRef<HTMLSpanElement>(null)
  const inView = useInView(ref, { once: true })
  const reduced = useReducedMotion()
  const [shown, setShown] = useState(text)
  useEffect(() => {
    if (!inView || reduced) return
    let raf = 0, start = 0
    const step = (now: number) => {
      start ||= now
      const revealed = Math.floor((now - start - delay * 1000) / speed)
      setShown([...text].map((c, i) => c === ' ' || i < revealed ? c : randomGlyph()).join(''))
      if (revealed < text.length) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [inView, reduced, text, delay, speed])
  return <span ref={ref}><span className="lp-sr">{text}</span><span aria-hidden="true">{shown}</span></span>
}

/** Animates 0 → 1 once the element is in view; the value is the final state under reduced motion. */
export function useRevealProgress(duration = 1.8) {
  const ref = useRef<HTMLUListElement>(null)
  const inView = useInView(ref, { once: true, margin: '-40px' })
  const reduced = useReducedMotion()
  const [progress, setProgress] = useState(0)
  useEffect(() => {
    if (!inView) return
    if (reduced) { setProgress(1); return }
    const controls = animate(0, 1, { duration, ease: [.16, 1, .3, 1], onUpdate: setProgress })
    return () => controls.stop()
  }, [inView, reduced, duration])
  return [ref, progress] as const
}

/** Pointer position for the CSS spotlight border on `.lp-glow` elements. */
export function spot(event: PointerEvent<HTMLElement>) {
  const el = event.currentTarget, r = el.getBoundingClientRect()
  el.style.setProperty('--mx', `${event.clientX - r.left}px`)
  el.style.setProperty('--my', `${event.clientY - r.top}px`)
}

/** Gentle pointer-driven 3D tilt with a moving glare. */
export function Tilt({ children, className }: { children: ReactNode; className?: string }) {
  const reduced = useReducedMotion()
  const x = useMotionValue(0), y = useMotionValue(0)
  const spring = { stiffness: 140, damping: 18 }
  const rotateX = useSpring(useTransform(y, [-.5, .5], [6, -6]), spring)
  const rotateY = useSpring(useTransform(x, [-.5, .5], [-8, 8]), spring)
  const glareX = useTransform(x, [-.5, .5], ['0%', '100%']), glareY = useTransform(y, [-.5, .5], ['0%', '100%'])
  const move = (event: PointerEvent<HTMLDivElement>) => {
    if (reduced || event.pointerType !== 'mouse') return
    const r = event.currentTarget.getBoundingClientRect()
    x.set((event.clientX - r.left) / r.width - .5); y.set((event.clientY - r.top) / r.height - .5)
  }
  const leave = () => { x.set(0); y.set(0) }
  return <motion.div className={className} style={{ rotateX, rotateY, transformPerspective: 1400, '--gx': glareX, '--gy': glareY } as never} onPointerMove={move} onPointerLeave={leave}>{children}</motion.div>
}

type Node = { x: number; y: number; vx: number; vy: number }
type Packet = { a: number; b: number; t: number; speed: number; hops: number }

/** Decorative network mesh: drifting nodes, packets routed along links, one anomalous node, pointer-reactive. */
export function SignalMesh({ className }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null)
  const reduced = useReducedMotion()
  useEffect(() => {
    const canvas = ref.current, ctx = canvas?.getContext('2d')
    if (!canvas || !ctx) return
    const LINK = 150, LINK2 = LINK * LINK, FOCUS = 190
    let w = 0, h = 0, raf = 0, running = false
    let nodes: Node[] = [], packets: Packet[] = []
    const mouse = { x: -1e4, y: -1e4 }

    const neighbours = (i: number) => nodes.flatMap((n, j) => j !== i && (n.x - nodes[i].x) ** 2 + (n.y - nodes[i].y) ** 2 < LINK2 ? [j] : [])
    const spawn = (a: number, hops = 0) => {
      const options = neighbours(a)
      if (options.length) packets.push({ a, b: options[Math.floor(Math.random() * options.length)], t: 0, speed: .008 + Math.random() * .012, hops })
    }

    const draw = (time: number) => {
      ctx.clearRect(0, 0, w, h)
      if (!reduced) for (const n of nodes) {
        n.x += n.vx; n.y += n.vy
        if (n.x < 0 || n.x > w) n.vx *= -1
        if (n.y < 0 || n.y > h) n.vy *= -1
      }
      const threat = nodes[0]
      for (let i = 0; i < nodes.length; i++) for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j], d2 = (a.x - b.x) ** 2 + (a.y - b.y) ** 2
        if (d2 > LINK2) continue
        const fade = 1 - Math.sqrt(d2) / LINK
        const near = Math.max(0, 1 - Math.hypot((a.x + b.x) / 2 - mouse.x, (a.y + b.y) / 2 - mouse.y) / FOCUS)
        const hostile = i === 0
        ctx.strokeStyle = hostile ? `rgba(239,68,68,${fade * .35})` : near > 0 ? `rgba(34,197,94,${fade * (.12 + near * .5)})` : `rgba(168,162,158,${fade * .17})`
        ctx.lineWidth = hostile || near > .3 ? 1 : .6
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke()
      }
      if (!reduced) {
        if (packets.length < 26 && Math.random() < .09) spawn(Math.floor(Math.random() * nodes.length))
        packets = packets.filter(p => {
          p.t += p.speed
          const a = nodes[p.a], b = nodes[p.b]
          if (p.t >= 1) { if (p.hops < 4 && Math.random() < .7) spawn(p.b, p.hops + 1); return false }
          if ((a.x - b.x) ** 2 + (a.y - b.y) ** 2 > LINK2 * 1.4) return false
          const x = a.x + (b.x - a.x) * p.t, y = a.y + (b.y - a.y) * p.t, red = p.a === 0 || p.b === 0
          ctx.fillStyle = red ? 'rgba(248,113,113,.95)' : 'rgba(74,222,128,.95)'
          ctx.shadowColor = red ? '#ef4444' : '#22c55e'; ctx.shadowBlur = 10
          ctx.beginPath(); ctx.arc(x, y, 1.8, 0, Math.PI * 2); ctx.fill()
          ctx.shadowBlur = 0
          return true
        })
      }
      for (let i = 0; i < nodes.length; i++) {
        const n = nodes[i], near = Math.max(0, 1 - Math.hypot(n.x - mouse.x, n.y - mouse.y) / FOCUS)
        ctx.fillStyle = i === 0 ? '#ef4444' : near > 0 ? `rgba(74,222,128,${.35 + near * .65})` : 'rgba(168,162,158,.45)'
        ctx.beginPath(); ctx.arc(n.x, n.y, i === 0 ? 3 : 1.4 + near * 1.4, 0, Math.PI * 2); ctx.fill()
      }
      const phase = (time / 2200) % 1
      ctx.strokeStyle = `rgba(239,68,68,${(1 - phase) * .6})`; ctx.lineWidth = 1
      ctx.beginPath(); ctx.arc(threat.x, threat.y, 4 + phase * 34, 0, Math.PI * 2); ctx.stroke()
    }

    const loop = (time: number) => { draw(time); raf = requestAnimationFrame(loop) }
    const setRunning = (on: boolean) => {
      if (reduced || on === running) return
      running = on
      if (on) raf = requestAnimationFrame(loop); else cancelAnimationFrame(raf)
    }
    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2), r = canvas.getBoundingClientRect()
      w = r.width; h = r.height
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      const count = Math.round(Math.min(95, Math.max(28, w * h / 13000)))
      nodes = Array.from({ length: count }, () => ({ x: Math.random() * w, y: Math.random() * h, vx: (Math.random() - .5) * .3, vy: (Math.random() - .5) * .3 }))
      nodes[0] = { x: w * .62, y: h * .42, vx: .05, vy: -.04 }
      packets = []
      if (reduced) draw(0)
    }
    const onPointer = (event: globalThis.PointerEvent) => { const r = canvas.getBoundingClientRect(); mouse.x = event.clientX - r.left; mouse.y = event.clientY - r.top }
    const sizer = new ResizeObserver(resize)
    const watcher = new IntersectionObserver(([entry]) => setRunning(entry.isIntersecting))
    sizer.observe(canvas); watcher.observe(canvas)
    window.addEventListener('pointermove', onPointer, { passive: true })
    return () => { cancelAnimationFrame(raf); sizer.disconnect(); watcher.disconnect(); window.removeEventListener('pointermove', onPointer) }
  }, [reduced])
  return <canvas ref={ref} className={className} aria-hidden="true" />
}
