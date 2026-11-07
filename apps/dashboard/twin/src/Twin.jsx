import React, { useMemo } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Html } from "@react-three/drei";

// GLUE-04 contract: items from TwinFeed.stream(sub_id)
// {kind, ref_id, at, provenance: LIVE|REPLAY|SYNTHETIC, payload, stale}
// Rover pose derives ONLY from rover_pose telemetry — never fabricated.
// Stale items render dimmed + flagged; incident markers link to
// incident_id + original evidence ref.

const STALE_COLOR = "#f59e0b";
const LIVE_COLOR = "#22c55e";

function RoverMarker({ pose, stale }) {
  if (!pose) return null;
  const { x = 0, y = 0, heading = 0 } = pose.payload;
  return (
    <group position={[x, 0.05, y]} rotation={[0, heading, 0]}>
      <mesh>
        <boxGeometry args={[0.4, 0.2, 0.6]} />
        <meshStandardMaterial
          color={stale ? STALE_COLOR : LIVE_COLOR}
          emissive={stale ? STALE_COLOR : "#000"}
        />
      </mesh>
      {stale && (
        <Html position={[0, 0.4, 0]} center>
          <div style={{ color: STALE_COLOR, fontSize: 12 }}>STALE</div>
        </Html>
      )}
    </group>
  );
}

function IncidentMarker({ item, onSelect }) {
  const { x = 0, z = 0, incident_id, title } = item.payload;
  return (
    <group position={[x, 0.1, z]} onClick={() => onSelect(item)}>
      <mesh>
        <sphereGeometry args={[0.15, 16, 16]} />
        <meshStandardMaterial color="#ef4444" />
      </mesh>
      <Html position={[0, 0.3, 0]} center>
        <div style={{ color: "#fff", fontSize: 10 }}>{title}</div>
      </Html>
    </group>
  );
}

function ZoneAssets({ zones }) {
  return zones.map((z) => (
    <mesh key={z.id} position={[z.x, 0.05, z.y]}>
      <boxGeometry args={[z.w || 1, 0.1, z.d || 1]} />
      <meshStandardMaterial color="#374151" wireframe />
    </mesh>
  ));
}

export default function Twin({ feed, zones = [], onSelectIncident }) {
  // feed = { subscribe()->sub_id, stream(sub_id)->FeedItem[] }
  const [subId, setSubId] = React.useState(null);
  const [items, setItems] = React.useState([]);

  React.useEffect(() => {
    // role+scope come from server-side session — never client claims
    const sid = feed.subscribe(currentUser());
    setSubId(sid);
    const poll = setInterval(() => setItems(feed.stream(sid)), 1000);
    return () => clearInterval(poll);
  }, [feed]);

  const rover = useMemo(
    () => [...items].reverse().find((i) => i.kind === "rover_pose"),
    [items]
  );
  const incidents = items.filter((i) => i.kind === "incident_marker");

  return (
    <Canvas camera={{ position: [8, 8, 8], fov: 50 }}>
      <ambientLight intensity={0.5} />
      <directionalLight position={[5, 10, 5]} />
      <gridHelper args={[20, 20]} />
      <ZoneAssets zones={zones} />
      <RoverMarker pose={rover} stale={rover?.stale} />
      {incidents.map((it) => (
        <IncidentMarker
          key={it.ref_id}
          item={it}
          onSelect={onSelectIncident}
        />
      ))}
      <OrbitControls />
    </Canvas>
  );
}

// session principal resolved server-side; placeholder until auth wiring
function currentUser() {
  return { role: "observer", incident_scope: [] };
}
