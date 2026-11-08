import { Suspense, useState } from 'react'
import { Canvas } from '@react-three/fiber'
import { Bloom, EffectComposer } from '@react-three/postprocessing'
import { RotateCcw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { CameraControls, FloorGrid, PatrolPath, RoverMarker, SecurityZone, SelectableObject, ServerRack, ThreatMarker, WireframeWall } from '@/lib/three/primitives'
import { usePhantomStore } from '@/store/use-phantom-store'
import { palette } from '@/styles/palette'

export default function DigitalTwinExample() {
  const glow = usePhantomStore(state => state.glow)
  const setGlow = usePhantomStore(state => state.setGlow)
  const selected = usePhantomStore(state => state.selectedDeviceId)
  const select = usePhantomStore(state => state.selectDevice)
  const [reset, setReset] = useState(0)
  return <div className="space-y-4">
    <div className="example-toolbar">
      <div className="flex items-center gap-3"><Switch id="glow" checked={glow} onCheckedChange={setGlow} /><Label htmlFor="glow">Postprocessing bloom</Label></div>
      <Button variant="outline" onClick={() => setReset(value => value + 1)}><RotateCcw />Reset camera</Button>
    </div>
    <div className="scene-frame" role="img" aria-label="Synthetic wireframe room with two server racks, rover, zone, and threat marker" data-testid="twin-scene">
      <Canvas camera={{ position: [10, 10, 12], fov: 45 }} dpr={[1, 1.5]} gl={{ antialias: false }} onPointerMissed={() => select(null)}>
        <color attach="background" args={[palette.background]} />
        <Suspense fallback={null}>
          <FloorGrid />
          <WireframeWall start={{ x: -5, y: -4 }} end={{ x: 5, y: -4 }} />
          <WireframeWall start={{ x: -5, y: -4 }} end={{ x: -5, y: 4 }} />
          <WireframeWall start={{ x: -5, y: 4 }} end={{ x: 5, y: 4 }} />
          <SecurityZone at={{ x: 2, y: 1 }} width={3} depth={3} />
          {[-2, 0].map((x, i) => <SelectableObject key={x} id={`rack-0${i + 1}`} onSelect={select}><ServerRack at={{ x, y: 2 }} selected={selected === `rack-0${i + 1}`} /></SelectableObject>)}
          <SelectableObject id="rover-01" onSelect={select}><RoverMarker at={{ x: 2, y: -2 }} heading={Math.PI / 4} /></SelectableObject>
          <SelectableObject id="sensor-01" onSelect={select}><ThreatMarker at={{ x: 3, y: 1 }} /></SelectableObject>
          <PatrolPath points={[{ x: -3, y: -2 }, { x: 2, y: -2 }, { x: 2, y: 2 }]} />
          <CameraControls resetKey={reset} />
          {glow && <EffectComposer multisampling={0}><Bloom intensity={0.4} luminanceThreshold={0.3} mipmapBlur /></EffectComposer>}
        </Suspense>
      </Canvas>
    </div>
    <div className="example-toolbar text-sm"><span>Drag to orbit · scroll to zoom · click an object</span><span role="status">Selected: <b>{selected ?? 'none'}</b></span></div>
    <div className="legend"><span className="text-[var(--phantom-wall)]">□ Walls</span><span className="text-[var(--phantom-infrastructure)]">□ Infrastructure</span><span className="text-[var(--phantom-healthy)]">◇ Rover / route</span><span className="text-[var(--phantom-threat)]">◆ Threat fixture</span></div>
    <p className="note">Authored geometry and a fixed rover pose. Coordinates are meters: map (x, y) → world (x, height, −y). This is a rendering example; no sensor reconstruction is inferred.</p>
  </div>
}
