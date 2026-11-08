import React from "react";
import ReactDOM from "react-dom/client";
import Twin from "./Twin.jsx";
import { DemoFeed } from "./demoFeed.js";

const ZONES = [
  { id: "rack-01", x: 2, y: 1, w: 2, d: 1.5 },
  { id: "lab-b", x: -3, y: -2, w: 3, d: 2 },
  { id: "lobby", x: 0, y: 4, w: 4, d: 2 },
  { id: "bench-row", x: -1, y: 0, w: 5, d: 1.5 },
];

const feed = new DemoFeed();

function App() {
  const [selected, setSelected] = React.useState(null);
  return (
    <>
      <div className="hud">
        <b>SENTINEL HIVE</b> - digital twin<br />
        <span className="demo">DEMO FEED - simulated telemetry</span><br />
        {selected ? (
          <span>
            incident: <b>{selected.payload.incident_id}</b><br />
            evidence: {selected.payload.evidence_id}
          </span>
        ) : (
          "click a red marker for incident + evidence"
        )}
      </div>
      <Twin feed={feed} zones={ZONES} onSelectIncident={setSelected} />
    </>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
