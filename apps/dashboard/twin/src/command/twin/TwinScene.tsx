import { Component, Suspense, useEffect, useMemo, useRef, useState, type ComponentRef, type ReactNode } from 'react'
import { Canvas, useFrame, useThree, type ThreeEvent } from '@react-three/fiber'
import { Edges, Html, Line, OrbitControls } from '@react-three/drei'
import { Bloom, EffectComposer } from '@react-three/postprocessing'
import { Color, DoubleSide, Group, Mesh, Vector3 } from 'three'
import { Box, Crosshair, Layers3, RotateCcw, ScanLine, Signal, Video } from 'lucide-react'
import { mapToWorld } from '@/lib/three/coordinates'
import { useCommandStore } from '../store'
import type { CameraMode, CommandState, Device, Point } from '../model'
import { createFacilityGrid, mergeCollinearWalls, occupancyToWalls } from './occupancy'
import './twin.css'

const colors = { cyan: '#eab308', purple: '#a8a29e', green: '#bfb6ab', red: '#ef4444', amber: '#fb923c', muted: '#a8a29e' }
const mapWalls = mergeCollinearWalls(occupancyToWalls(createFacilityGrid()))
const home: Point = { x: 18, y: 3 }
const patrol: Point[] = [{ x: 18, y: 3 }, { x: 18, y: 4.5 }, { x: 14, y: 4.5 }, { x: 13, y: 4.5 }, { x: 13, y: 13.5 }, { x: 14, y: 13.5 }, { x: 18, y: 13.5 }, { x: 18, y: 9 }, { x: 18, y: 3 }]
const cameraModes: { id: CameraMode; label: string; icon: typeof Box }[] = [{ id: 'isometric', label: 'Isometric', icon: Box }, { id: 'top', label: 'Top down', icon: Layers3 }, { id: 'orbit', label: 'Orbit', icon: RotateCcw }, { id: 'follow', label: 'Follow rover', icon: Video }]

export function useReducedMotion() {
  const [reduced, setReduced] = useState(() => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches)
  useEffect(() => { const query = window.matchMedia('(prefers-reduced-motion: reduce)'); const update = () => setReduced(query.matches); query.addEventListener('change', update); return () => query.removeEventListener('change', update) }, [])
  return reduced
}

class SceneBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  render() { return this.state.failed ? <div className="twin-fallback"><Box size={30} /><strong>Spatial view unavailable</strong><span>Your browser could not initialize WebGL. Facility entities remain available below and in the network workspace.</span></div> : this.props.children }
}

function Pickable({ id, children }: { id: string; children: ReactNode }) {
  const select = useCommandStore(s => s.select)
  const gl = useThree(s => s.gl)
  return <group onClick={(event: ThreeEvent<MouseEvent>) => { event.stopPropagation(); select(id) }} onPointerOver={event => { event.stopPropagation(); gl.domElement.style.cursor = 'pointer' }} onPointerOut={() => { gl.domElement.style.cursor = 'grab' }}>{children}</group>
}

function Floor({ heatmap }: { heatmap: boolean }) {
  const points = useMemo(() => {
    const result: [number, number, number][] = []
    for (let x = 0; x <= 24; x += 1) result.push([x, -0.01, 0], [x, -0.01, -18])
    for (let y = 0; y <= 18; y += 1) result.push([0, -0.01, -y], [24, -0.01, -y])
    return result
  }, [])
  return <group>
    <mesh position={[12, -0.12, -9]}><boxGeometry args={[24.7, 0.2, 18.7]} /><meshBasicMaterial color="#151413" /><Edges color="#43403c" /></mesh>
    <Line points={points} segments color="#3c3936" transparent opacity={0.5} lineWidth={0.5} />
    <Line points={[[0, 0.015, 0], [24, 0.015, 0], [24, 0.015, -18], [0, 0.015, -18], [0, 0.015, 0]]} color={colors.cyan} transparent opacity={0.65} lineWidth={1.5} />
    {[0, 4, 8, 12, 16, 20, 24].map(x => <group key={x} position={[x, 0.03, 0.5]}><Line points={[[0, 0, -0.25], [0, 0, 0.05]]} color={colors.muted} transparent opacity={0.6} /><Html center transform rotation={[-Math.PI / 2, 0, 0]} distanceFactor={9} className="twin-axis-label">{String(x).padStart(2, '0')}</Html></group>)}
    {heatmap && <mesh position={[7, 0.01, -9]} rotation={[-Math.PI / 2, 0, 0]}><planeGeometry args={[13.6, 17.5]} /><meshBasicMaterial color={colors.purple} transparent opacity={0.035} depthWrite={false} /></mesh>}
  </group>
}

function Walls() {
  return <group>{mapWalls.map(wall => <mesh key={wall.id} position={[(wall.start.x + wall.end.x) / 2, 1.45, -wall.start.y]}>
    <boxGeometry args={[wall.end.x - wall.start.x, 2.9, wall.thickness]} />
    <meshBasicMaterial color={colors.cyan} transparent opacity={0.035} depthWrite={false} />
    <Edges color={colors.cyan} transparent opacity={0.56} />
  </mesh>)}</group>
}

function Rack({ device, selected, labels }: { device: Device; selected: boolean; labels: boolean }) {
  const faceLines = useMemo(() => Array.from({ length: 6 }, (_, i) => [[-0.56, 0.4 + i * 0.32, 0.636], [0.56, 0.4 + i * 0.32, 0.636]]).flat() as [number, number, number][], [])
  const color = device.status === 'threat' ? colors.red : selected ? '#e7e5e4' : colors.purple
  return <Pickable id={device.id}><group position={mapToWorld(device.position)}>
    <mesh position={[0, 1.3, 0]}><boxGeometry args={[1.45, 2.6, 1.25]} /><meshBasicMaterial color="#1f1d1c" transparent opacity={0.88} /><Edges color={color} transparent opacity={selected ? 1 : 0.75} /></mesh>
    <mesh position={[0, 1.28, 0.635]}><planeGeometry args={[1.15, 2.2]} /><meshBasicMaterial color="#2d2b29" transparent opacity={0.8} /></mesh>
    <Line points={faceLines} segments color={color} transparent opacity={0.45} lineWidth={1} />
    {[0.58, 1.22, 1.86].map(y => <mesh key={y} position={[0.42, y, 0.65]}><boxGeometry args={[0.14, 0.04, 0.02]} /><meshBasicMaterial color={device.status === 'threat' ? colors.red : colors.green} toneMapped={false} /></mesh>)}
    <mesh position={[0, 2.64, 0]}><boxGeometry args={[1.54, 0.08, 1.34]} /><meshBasicMaterial color={color} transparent opacity={0.25} /></mesh>
    {selected && <mesh position={[0, 0.025, 0]} rotation={[-Math.PI / 2, 0, 0]}><ringGeometry args={[1.05, 1.1, 40]} /><meshBasicMaterial color={colors.cyan} toneMapped={false} /></mesh>}
    {(labels || selected) && <Html position={[0, 3.08, 0]} center distanceFactor={29} zIndexRange={[12, 0]}><button className={`twin-object-label ${selected ? 'is-selected' : ''}`} onClick={event => { event.stopPropagation(); useCommandStore.getState().select(device.id) }}>{device.id.replace('rack-', 'R')}</button></Html>}
  </group></Pickable>
}

function Equipment({ device, selected, heatmap, reduced, running }: { device: Device; selected: boolean; heatmap: boolean; reduced: boolean; running: boolean }) {
  const sweep = useRef<Mesh>(null)
  useFrame(({ clock }) => { if (sweep.current && !reduced && running) { const scale = 0.55 + ((clock.elapsedTime * 0.22 + device.position.x * 0.1) % 1) * 0.7; sweep.current.scale.setScalar(scale) } })
  const ap = device.kind === 'ap'
  const color = device.status === 'threat' ? colors.red : selected ? '#e7e5e4' : ap ? colors.cyan : colors.amber
  return <Pickable id={device.id}><group position={mapToWorld(device.position)}>
    <mesh position={[0, ap ? 2.3 : 0.85, 0]}><cylinderGeometry args={[ap ? 0.29 : 0.18, ap ? 0.29 : 0.18, ap ? 0.13 : 1.7, 8]} /><meshBasicMaterial color="#272523" /><Edges color={color} /></mesh>
    <mesh position={[0, ap ? 2.39 : 1.8, 0]} rotation={[-Math.PI / 2, 0, 0]}><ringGeometry args={[0.15, 0.21, 16]} /><meshBasicMaterial color={color} side={DoubleSide} toneMapped={false} /></mesh>
    {heatmap && ap && <group rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.03, 0]}>{[1, 2, 3].map(radius => <mesh key={radius}><circleGeometry args={[radius * 1.35, 48]} /><meshBasicMaterial color={color} transparent opacity={0.018} depthWrite={false} /></mesh>)}<mesh ref={sweep}><ringGeometry args={[3.8, 3.84, 64]} /><meshBasicMaterial color={color} transparent opacity={0.2} depthWrite={false} /></mesh></group>}
    {selected && <Html position={[0, 3, 0]} center zIndexRange={[15, 0]}><div className="twin-object-label is-selected">{device.name}</div></Html>}
  </group></Pickable>
}

function ZoneOverlays({ state, labels }: { state: CommandState; labels: boolean }) {
  const select = useCommandStore(s => s.select)
  return <group>{state.zones.map((zone, index) => {
    const incident = state.incidents.find(item => item.zoneId === zone.id && item.status !== 'resolved')
    const extents: [number, number, number, number][] = [[0.35, 0.35, 13.3, 17.3], [14.35, 9.35, 9.3, 8.3], [14.35, 0.35, 9.3, 8.3]]
    const [x, y, width, depth] = extents[index] ?? extents[0]
    return <group key={zone.id}>
      <mesh position={[x + width / 2, 0.018, -(y + depth / 2)]} rotation={[-Math.PI / 2, 0, 0]}><planeGeometry args={[width, depth]} /><meshBasicMaterial color={incident ? colors.red : zone.color} transparent opacity={incident ? 0.085 : 0.025} depthWrite={false} /></mesh>
      {labels && <Html position={[x + 2.3, 0.2, -(y + depth - 0.8)]} center zIndexRange={[10, 0]}><button className={`twin-zone-label ${incident ? 'has-threat' : ''}`} onClick={() => select(incident?.id ?? zone.id)}><span>{zone.code}</span>{zone.name}</button></Html>}
    </group>
  })}</group>
}

function Threat({ id, at, reduced }: { id: string; at: Point; reduced: boolean }) {
  const marker = useRef<Group>(null)
  useFrame(({ clock }) => { if (marker.current && !reduced) marker.current.position.y = 3.8 + Math.sin(clock.elapsedTime * 1.6) * 0.08 })
  return <Pickable id={id}><group position={mapToWorld(at)}>
    <mesh position={[0, 0.07, 0]} rotation={[-Math.PI / 2, 0, 0]}><ringGeometry args={[0.9, 0.94, 48]} /><meshBasicMaterial color={colors.red} transparent opacity={0.75} toneMapped={false} /></mesh>
    <Line points={[[0, 0.08, 0], [0, 3.6, 0]]} color={colors.red} dashed dashSize={0.13} gapSize={0.12} transparent opacity={0.5} />
    <group ref={marker} position={[0, 3.8, 0]}><mesh><octahedronGeometry args={[0.27]} /><meshBasicMaterial color={colors.red} toneMapped={false} /></mesh><Html position={[0, 0.6, 0]} center zIndexRange={[20, 0]}><button className="twin-threat-label" onClick={() => useCommandStore.getState().select(id)}>INCIDENT</button></Html></group>
  </group></Pickable>
}

function Rover({ state, selected, reduced }: { state: CommandState; selected: boolean; reduced: boolean }) {
  const rover = useRef<Group>(null)
  const scanner = useRef<Group>(null)
  const initialPosition = useRef(mapToWorld(state.rover.position, 0.12))
  const target = useMemo(() => new Vector3(...mapToWorld(state.rover.position, 0.12)), [state.rover.position])
  const color = state.rover.stopped ? colors.red : colors.green
  useFrame((_, delta) => {
    if (rover.current) {
      rover.current.position.lerp(target, reduced || state.rover.stopped ? 1 : Math.min(1, delta * 8))
      const angle = Math.atan2(Math.sin(state.rover.heading - rover.current.rotation.y), Math.cos(state.rover.heading - rover.current.rotation.y))
      rover.current.rotation.y += angle * (reduced ? 1 : Math.min(1, delta * 7))
    }
    if (scanner.current && !reduced && !state.rover.stopped && state.simulation === 'running') scanner.current.rotation.y += delta * 0.7
  })
  return <Pickable id="rover-01"><group ref={rover} position={initialPosition.current}>
    <mesh position={[0, 0.28, 0]}><boxGeometry args={[1.05, 0.38, 0.68]} /><meshBasicMaterial color="#35322f" /><Edges color={color} /></mesh>
    <mesh position={[0.05, 0.54, 0]}><boxGeometry args={[0.55, 0.17, 0.45]} /><meshBasicMaterial color="#57534e" /><Edges color={color} /></mesh>
    <mesh position={[0.13, 0.74, 0]}><cylinderGeometry args={[0.12, 0.12, 0.23, 12]} /><meshBasicMaterial color={color} toneMapped={false} /></mesh>
    {[-0.36, 0.36].flatMap(x => [-0.38, 0.38].map(z => <mesh key={`${x}-${z}`} position={[x, 0.16, z]} rotation={[Math.PI / 2, 0, 0]}><cylinderGeometry args={[0.18, 0.18, 0.12, 12]} /><meshBasicMaterial color="#1d1c1a" /><Edges color="#68635d" /></mesh>))}
    <mesh position={[0.72, 0.08, 0]} rotation={[0, 0, -Math.PI / 2]}><coneGeometry args={[0.22, 0.42, 3]} /><meshBasicMaterial color={color} toneMapped={false} /></mesh>
    <group ref={scanner}><mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.04, 0]}><circleGeometry args={[2.8, 32, 0, Math.PI / 6]} /><meshBasicMaterial color={color} transparent opacity={0.075} depthWrite={false} side={DoubleSide} /></mesh></group>
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.02, 0]}><ringGeometry args={[selected ? 1.05 : 0.85, selected ? 1.1 : 0.87, 48]} /><meshBasicMaterial color={color} transparent opacity={0.8} toneMapped={false} /></mesh>
    <Html position={[0, 1.7, 0]} center zIndexRange={[16, 0]}><button className={`twin-rover-label ${state.rover.stopped ? 'is-stopped' : ''} ${state.rover.stale ? 'is-stale' : ''}`} onClick={() => useCommandStore.getState().select('rover-01')}><span />PHANTOM 01{state.rover.stale ? ' ·STALE' : ''}</button></Html>
  </group></Pickable>
}

function Cameras({ state, reset, reduced }: { state: CommandState; reset: number; reduced: boolean }) {
  const controls = useRef<ComponentRef<typeof OrbitControls>>(null)
  const initialTarget = useMemo(() => new Vector3(12, 0, -9), [])
  const camera = useThree(s => s.camera)
  const cameraMode = useCommandStore(s => s.camera)
  const selected = useCommandStore(s => s.selectedId)
  const lastInteraction = useRef(-Infinity)
  const manualStart = useRef(new Vector3())
  const interacting = useRef(false)
  const moving = useRef(true)
  const goal = useRef({ position: new Vector3(36, 29, 17), target: new Vector3(12, 0, -9) })
  const previousIncident = useRef<string | null>(null)
  const latestIncident = state.incidents.find(incident => incident.status !== 'resolved')
  useEffect(() => {
    const target = new Vector3(12, 0, -9)
    const offset = cameraMode === 'top' ? new Vector3(0, 41, 0.01) : cameraMode === 'orbit' ? new Vector3(26, 18, 26) : cameraMode === 'follow' ? new Vector3(8, 9, 10) : new Vector3(24, 29, 26)
    if (cameraMode === 'follow') target.set(...mapToWorld(useCommandStore.getState().state.rover.position))
    goal.current = { position: target.clone().add(offset), target }
    moving.current = true
    lastInteraction.current = -Infinity
  }, [cameraMode, reset])
  useEffect(() => {
    if (!selected || interacting.current || performance.now() - lastInteraction.current < 1800 || cameraMode === 'follow') return
    const current = useCommandStore.getState().state
    const entity = current.devices.find(device => device.id === selected)
    const incident = current.incidents.find(item => item.id === selected)
    const zone = current.zones.find(item => item.id === (incident?.zoneId ?? selected))
    const point = selected === 'rover-01' ? current.rover.position : entity?.position ?? zone?.position
    if (!point) return
    const target = new Vector3(...mapToWorld(point, 0.5))
    const offset = cameraMode === 'top' ? new Vector3(0, 24, 0.01) : new Vector3(14, 16, 16)
    goal.current = { position: target.clone().add(offset), target }
    moving.current = true
  }, [selected, cameraMode])
  useEffect(() => {
    if (!latestIncident || previousIncident.current === latestIncident.id) return
    previousIncident.current = latestIncident.id
    if (interacting.current || performance.now() - lastInteraction.current < 8000 || cameraMode === 'follow') return
    const zone = state.zones.find(item => item.id === latestIncident.zoneId)
    if (!zone) return
    const target = new Vector3(...mapToWorld(zone.position))
    goal.current = { position: target.clone().add(cameraMode === 'top' ? new Vector3(0, 30, 0.01) : new Vector3(20, 24, 22)), target }
    moving.current = true
  }, [latestIncident, state.zones, cameraMode])
  useFrame((_, delta) => {
    if (!controls.current) return
    if (cameraMode === 'follow' && performance.now() - lastInteraction.current > 8000) {
      goal.current.target.set(...mapToWorld(state.rover.position))
      goal.current.position.copy(goal.current.target).add(new Vector3(8, 9, 10))
      moving.current = true
    }
    if (!moving.current) return
    const alpha = reduced ? 1 : 1 - Math.exp(-delta * 3.5)
    camera.position.lerp(goal.current.position, alpha)
    controls.current.target.lerp(goal.current.target, alpha)
    controls.current.update()
    if (cameraMode !== 'follow' && camera.position.distanceTo(goal.current.position) < 0.02) moving.current = false
  })
  return <OrbitControls ref={controls} target={initialTarget} makeDefault enableDamping={!reduced} dampingFactor={0.09} minDistance={7} maxDistance={68} maxPolarAngle={Math.PI / 2.05} onStart={() => { manualStart.current.copy(camera.position); interacting.current = true; moving.current = false }} onEnd={() => { interacting.current = false; if (manualStart.current.distanceTo(camera.position) > 0.08) lastInteraction.current = performance.now() }} />
}

function Facility({ labels, heatmap, routes, reset, compact, reduced }: { labels: boolean; heatmap: boolean; routes: boolean; reset: number; compact: boolean; reduced: boolean }) {
  const state = useCommandStore(s => s.state)
  const selected = useCommandStore(s => s.selectedId)
  const linkedDevices = state.incidents.find(item => item.id === selected)?.deviceIds ?? []
  const activeMission = state.missions.find(item => item.id === state.rover.missionId && item.status !== 'complete' && item.status !== 'cancelled')
  const remainingRoute = activeMission?.route?.slice(activeMission.routeIndex ?? 0)
  const route = activeMission ? [state.rover.position, ...(remainingRoute?.length ? remainingRoute : [activeMission.target])] : patrol
  return <>
    <color attach="background" args={['#0a0807']} />
    <ambientLight intensity={1} />
    <Floor heatmap={heatmap} />
    <ZoneOverlays state={state} labels={labels} />
    <Walls />
    {state.devices.filter(device => device.kind === 'server').map(device => <Rack key={device.id} device={device} selected={selected === device.id || linkedDevices.includes(device.id)} labels={labels && !compact} />)}
    {state.devices.filter(device => device.kind === 'ap' || device.kind === 'sensor').map(device => <Equipment key={device.id} device={device} selected={selected === device.id || linkedDevices.includes(device.id)} heatmap={heatmap} reduced={reduced} running={state.simulation === 'running'} />)}
    {routes && <Line points={route.map(point => mapToWorld(point, 0.06))} color={colors.green} dashed dashSize={0.3} gapSize={0.18} lineWidth={1.8} transparent opacity={0.7} />}
    <mesh position={mapToWorld(home, 0.03)} rotation={[-Math.PI / 2, 0, 0]}><ringGeometry args={[0.6, 0.65, 4]} /><meshBasicMaterial color={colors.green} transparent opacity={0.5} /></mesh>
    <Rover state={state} selected={selected === 'rover-01'} reduced={reduced} />
    {state.incidents.filter(incident => incident.status !== 'resolved').slice(0, 4).map(incident => { const point = state.devices.find(device => incident.deviceIds.includes(device.id))?.position ?? state.zones.find(zone => zone.id === incident.zoneId)?.position; return point ? <Threat key={incident.id} id={incident.id} at={point} reduced={reduced} /> : null })}
    <Cameras state={state} reset={reset} reduced={reduced} />
    {<EffectComposer multisampling={0}><Bloom intensity={compact ? 0.2 : 0.36} luminanceThreshold={0.8} luminanceSmoothing={0.3} mipmapBlur /></EffectComposer>}
  </>
}

export default function TwinScene({ compact = false }: { compact?: boolean }) {
  const mode = useCommandStore(s => s.camera)
  const appMode = useCommandStore(s => s.mode)
  const setCamera = useCommandStore(s => s.setCamera)
  const state = useCommandStore(s => s.state)
  const select = useCommandStore(s => s.select)
  const [labels, setLabels] = useState(true)
  const [heatmap, setHeatmap] = useState(true)
  const [routes, setRoutes] = useState(true)
  const [reset, setReset] = useState(0)
  const reduced = useReducedMotion()
  return <div className={`twin-scene ${compact ? 'twin-scene-compact' : ''}`} aria-label="Interactive simulated facility digital twin">
    <div className="twin-scene-grid" />
    <div className="twin-scene-status"><span className="twin-status-dot" /><span>SPATIAL MESH</span><i>0.25 M / CELL</i></div>
    <div className="twin-scene-bearing"><span>N</span><span>↑</span><span>MAP FRAME</span></div>
    <SceneBoundary><Suspense fallback={<div className="twin-fallback">Initializing spatial mesh…</div>}><Canvas camera={{ position: [36, 29, 17], fov: 40, near: 0.1, far: 180 }} dpr={[1, 1.5]} gl={{ antialias: true, alpha: false, powerPreference: 'high-performance' }} onCreated={({ gl }) => { gl.setClearColor(new Color('#0a0807')); gl.domElement.setAttribute('aria-label', '3D facility: drag to orbit, scroll to zoom; select equipment using entity controls below') }} fallback={<div className="twin-fallback">WebGL is unavailable. Use the entity controls to inspect this simulated facility.</div>}>
      <Facility labels={labels} heatmap={heatmap} routes={routes} reset={reset} compact={compact} reduced={reduced} />
    </Canvas></Suspense></SceneBoundary>
    <div className="twin-camera-controls" aria-label="Digital twin camera">{cameraModes.map(({ id, label, icon: Icon }) => <button key={id} title={label} aria-label={`${label} camera`} aria-pressed={mode === id} className={mode === id ? 'is-active' : ''} onClick={() => setCamera(id)}><Icon size={14} />{!compact && <span>{label}</span>}</button>)}<span className="twin-controls-divider" /><button aria-label="Reset camera" title="Reset camera" onClick={() => { select(null); setCamera('isometric'); setReset(value => value + 1) }}><Crosshair size={14} /></button></div>
    {!compact && <div className="twin-layer-controls" aria-label="Digital twin layers"><button aria-pressed={labels} onClick={() => setLabels(value => !value)}><Box size={13} />Labels</button><button aria-pressed={heatmap} onClick={() => setHeatmap(value => !value)}><Signal size={13} />RF field</button><button aria-pressed={routes} onClick={() => setRoutes(value => !value)}><ScanLine size={13} />Route</button></div>}
    <div className="twin-scene-footer"><span>FACILITY A <i>/</i> LEVEL 01</span><span>{state.rover.position.x.toFixed(1)}, {state.rover.position.y.toFixed(1)} <i>M</i></span><span>{state.rover.stale ? 'TELEMETRY STALE' : appMode === 'live' ? 'LIVE TELEMETRY' : 'DEMO TELEMETRY'}</span></div>
  </div>
}
