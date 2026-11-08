import { Line, OrbitControls } from '@react-three/drei'
import { useThree, type ThreeEvent } from '@react-three/fiber'
import { useEffect, type ReactNode } from 'react'
import { palette } from '@/styles/palette'
import { mapToWorld, wallFromEndpoints, type MapFrame, type MapPoint } from './coordinates'

export function WireframeWall({ start, end, height = 2, frame }: { start: MapPoint; end: MapPoint; height?: number; frame?: MapFrame }) {
  const wall = wallFromEndpoints(start, end, height, 0.06, frame)
  return <mesh position={wall.position} rotation={wall.rotation}>
    <boxGeometry args={wall.size} /><meshBasicMaterial color={palette.wall} wireframe />
  </mesh>
}
export function FloorGrid({ size = 16, divisions = 16 }: { size?: number; divisions?: number }) {
  return <gridHelper args={[size, divisions, palette.wall, palette.panel]} />
}
export function SelectableObject({ id, onSelect, children }: { id: string; onSelect: (id: string) => void; children: ReactNode }) {
  return <group onClick={(event: ThreeEvent<MouseEvent>) => { event.stopPropagation(); onSelect(id) }}>{children}</group>
}
export function ServerRack({ at, selected = false, frame }: { at: MapPoint; selected?: boolean; frame?: MapFrame }) {
  return <mesh position={mapToWorld(at, 0.9, frame)}>
    <boxGeometry args={[0.8, 1.8, 0.9]} />
    <meshBasicMaterial color={selected ? palette.text : palette.infrastructure} wireframe />
  </mesh>
}
/** Heading is radians counterclockwise from map +x. Marker nose points local +X. */
export function RoverMarker({ at, heading = 0, frame }: { at: MapPoint; heading?: number; frame?: MapFrame }) {
  return <group position={mapToWorld(at, 0.2, frame)} rotation={[0, heading, 0]}>
    <mesh><boxGeometry args={[0.7, 0.28, 0.45]} /><meshBasicMaterial color={palette.healthy} wireframe /></mesh>
    <mesh position={[0.45, 0, 0]} rotation={[0, 0, -Math.PI / 2]}>
      <coneGeometry args={[0.15, 0.3, 4]} /><meshBasicMaterial color={palette.healthy} toneMapped={false} />
    </mesh>
  </group>
}
export function SecurityZone({ at, width, depth, frame }: { at: MapPoint; width: number; depth: number; frame?: MapFrame }) {
  return <mesh position={mapToWorld(at, 0.015, frame)} rotation={[-Math.PI / 2, 0, 0]}>
    <planeGeometry args={[width, depth]} /><meshBasicMaterial color={palette.warning} transparent opacity={0.1} depthWrite={false} />
  </mesh>
}
export function ThreatMarker({ at, frame }: { at: MapPoint; frame?: MapFrame }) {
  return <mesh position={mapToWorld(at, 0.5, frame)}>
    <octahedronGeometry args={[0.24]} /><meshBasicMaterial color={palette.threat} toneMapped={false} />
  </mesh>
}
export function PatrolPath({ points, frame }: { points: MapPoint[]; frame?: MapFrame }) {
  return <Line points={points.map(point => mapToWorld(point, 0.04, frame))} color={palette.healthy} dashed dashSize={0.2} gapSize={0.12} lineWidth={1} />
}
export function CameraControls({ resetKey = 0 }: { resetKey?: number }) {
  const camera = useThree(state => state.camera)
  useEffect(() => { camera.position.set(10, 10, 12); camera.lookAt(0, 0, 0) }, [camera, resetKey])
  return <OrbitControls key={resetKey} makeDefault minDistance={4} maxDistance={30} maxPolarAngle={Math.PI / 2.05} />
}
