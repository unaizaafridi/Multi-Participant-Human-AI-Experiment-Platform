import { useEffect, useState } from "react";

function getPid() {
  // sessionStorage = one id per browser tab, so several tabs act as several players
  let pid = sessionStorage.getItem("pid");
  if (!pid) {
    pid = crypto.randomUUID();
    sessionStorage.setItem("pid", pid);
  }
  return pid;
}

export default function App() {
  const [view, setView] = useState({ type: "connecting" });

  useEffect(() => {
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(
      `${protocol}://${window.location.host}/ws/session?pid=${getPid()}`
    );
    ws.onmessage = (e) => setView(JSON.parse(e.data));
    ws.onclose = () => setView((v) => ({ ...v, closed: true }));
    return () => ws.close();
  }, []);

  return (
    <div style={{ fontFamily: "sans-serif", padding: 24 }}>
      <h1>Group Decision Experiment</h1>
      {view.type === "connecting" && <p>Connecting...</p>}
      {view.type === "waiting" && <p>Waiting for other participants...</p>}
      {view.type === "session_started" && (
        <div>
          <p>Session started. You are <b>{view.you}</b>.</p>
          <p>Participants: {view.players.join(", ")}</p>
        </div>
      )}
      {view.closed && <p style={{ color: "crimson" }}>Connection closed.</p>}
      <details style={{ marginTop: 24 }}>
        <summary>Raw message (debug)</summary>
        <pre>{JSON.stringify(view, null, 2)}</pre>
      </details>
    </div>
  );
}