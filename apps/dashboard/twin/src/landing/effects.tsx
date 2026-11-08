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
