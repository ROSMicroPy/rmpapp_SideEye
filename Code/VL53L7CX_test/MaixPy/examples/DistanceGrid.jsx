import { useEffect, useState } from "react";

// Copy into your React app: <DistanceGrid baseUrl="http://192.168.1.50" />
export default function DistanceGrid({ baseUrl }) {
  const [frame, setFrame] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let stopped = false;
    let timer;
    let controller;
    setFrame(null);
    setError("");
    async function poll() {
      controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 4000);
      try {
        const response = await fetch(`${baseUrl.replace(/\/$/, "")}/api/frame`, {
          signal: controller.signal,
          cache: "no-store",
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
        if (!stopped) {
          setFrame(data);
          setError("");
        }
      } catch (err) {
        if (!stopped) {
          setError(err.name === "AbortError" ? "Sensor request timed out" : err.message);
          setFrame(null);
        }
      } finally {
        clearTimeout(timeout);
        // Schedule after completion so requests never overlap.
        if (!stopped) timer = setTimeout(poll, 100);
      }
    }
    poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
      controller?.abort();
    };
  }, [baseUrl]);

  if (error) return <p role="alert">Sensor unavailable: {error}</p>;
  if (!frame) return <p>Waiting for sensor…</p>;
  return (
    <figure style={{ maxWidth: 560, margin: 0 }}>
      <figcaption>VL53L7CX · {frame.rows}×{frame.cols} · millimeters</figcaption>
      <div style={{ display: "grid", gridTemplateColumns: `repeat(${frame.cols}, 1fr)`, gap: 3 }}>
        {frame.distance_mm.flat().map((mm, i) => (
          <div key={i} title={`Zone ${i}: ${mm === null ? "no valid target" : `${mm} mm`}`}
            style={{ aspectRatio: "1", display: "grid", placeItems: "center", fontSize: 12,
              color: "white", background: mm === null ? "#444" :
                `hsl(${Math.min(1, Math.max(0, mm / 4000)) * 240} 75% 32%)` }}>
            {mm ?? "—"}
          </div>
        ))}
      </div>
      <p>Red: near · Blue: far (4 m scale) · Gray: invalid</p>
    </figure>
  );
}
