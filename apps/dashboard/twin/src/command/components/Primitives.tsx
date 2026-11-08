import { useEffect, useRef, type ReactNode } from 'react'
import { gsap } from 'gsap'
import { useReducedMotion } from 'motion/react'
import { GripHorizontal } from 'lucide-react'

export function Panel({ title, label, actions, children, className = '', drag = false }: { title: string; label?: string; actions?: ReactNode; children: ReactNode; className?: string; drag?: boolean }) {
  return <section className={`pc-panel ${className}`}><header className={`pc-panel-head ${drag ? 'pc-drag' : ''}`}><div className="pc-panel-title">{drag && <GripHorizontal size={13} />}<h2>{title}</h2>{label && <span className="pc-eyebrow">{label}</span>}</div>{actions}</header>{children}</section>
}
export function AnimatedNumber({ value, decimals = 0 }: { value: number; decimals?: number }) {
  const element = useRef<HTMLSpanElement>(null)
  const current = useRef({ value })
  const reduced = useReducedMotion()
  useEffect(() => {
    if (!element.current) return
    if (reduced) { element.current.textContent = value.toFixed(decimals); current.current.value = value; return }
    const tween = gsap.to(current.current, { value, duration: .7, ease: 'power2.out', onUpdate: () => { if (element.current) element.current.textContent = current.current.value.toFixed(decimals) } })
    return () => { tween.kill() }
  }, [value, decimals, reduced])
  return <span ref={element}>{value.toFixed(decimals)}</span>
}
export function Sparkline({ values, color = '#36CFF4' }: { values: number[]; color?: string }) {
  const min = Math.min(...values) - 2, range = Math.max(...values) - min + 2
  const path = values.map((v, i) => `${i * 100 / Math.max(1, values.length - 1)},${30 - ((v - min) / range) * 26}`).join(' ')
  return <svg viewBox="0 0 100 34" className="pc-sparkline" aria-hidden="true"><polyline points={path} fill="none" stroke={color} strokeWidth="1.5" vectorEffect="non-scaling-stroke" /></svg>
}
export function Status({ children, tone = 'cyan' }: { children: ReactNode; tone?: string }) { return <span className={`pc-chip pc-${tone}`}><span className="pc-dot" />{children}</span> }
