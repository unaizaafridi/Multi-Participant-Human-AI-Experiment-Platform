import { useEffect, useState } from "react";

export default function App() {
  const [health, setHealth] = useState(null);
  const [error, setError] = useState(null);
  const [wsLog, setWsLog] = useState([]);

  useEffect(() => {
    fetch("/api/health")
      .then((r) => r.json())
      .then(setHealth)
      .catch((e) => setError(String(e)));

    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${protocol}://${window.location.host}/ws/echo`);
    const log = (line) => setWsLog((prev) => [...prev, line]);

    ws.onopen = () => {
      log("connected");
      ws.send("hello from React");
    };
    ws.onmessage = (e) => log(`server says: ${e.data}`);
    ws.onerror = () => log("error");
    ws.onclose = () => log("closed");

    return () => ws.close();
  }, []);

  return (
    <div style={{ fontFamily: "sans-serif", padding: 24 }}>
      <h1>Group Decision Experiment</h1>

      <h3>Backend health</h3>
      {error && <p style={{ color: "crimson" }}>Error: {error}</p>}
      {health ? <pre>{JSON.stringify(health, null, 2)}</pre> : <p>Loading...</p>}

      <h3>WebSocket test</h3>
      <pre>{wsLog.join("\n")}</pre>
    </div>
  );
}