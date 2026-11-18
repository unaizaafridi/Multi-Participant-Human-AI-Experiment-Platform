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

const PHASE_TITLES = {
  discuss: "Discussion",
  vote: "Voting",
  results: "Results",
};

export default function App() {
  const [status, setStatus] = useState("connecting"); // connecting | waiting | running | closed
  const [info, setInfo] = useState(null);             // { you, players }
  const [phase, setPhase] = useState(null);           // last state_changed message
  const [endsAt, setEndsAt] = useState(0);            // local time when the phase ends
  const [now, setNow] = useState(Date.now());
  const [lastMsg, setLastMsg] = useState(null);

  useEffect(() => {
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(
      `${protocol}://${window.location.host}/ws/session?pid=${getPid()}`
    );
    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      setLastMsg(msg);
      if (msg.type === "waiting") setStatus("waiting");
      if (msg.type === "session_started") {
        setInfo({ you: msg.you, players: msg.players });
        setStatus("running");
      }
      if (msg.type === "state_changed") {
        setPhase(msg);
        setEndsAt(Date.now() + msg.seconds_left * 1000);
      }
    };
    ws.onclose = () => setStatus("closed");
    return () => ws.close();
  }, []);

  // Tick every 250 ms so the countdown stays smooth
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(t);
  }, []);

  const secondsLeft = Math.max(0, Math.ceil((endsAt - now) / 1000));

  return (
    <div style={{ fontFamily: "sans-serif", padding: 24 }}>
      <h1>Group Decision Experiment</h1>
      {status === "connecting" && <p>Connecting...</p>}
      {status === "waiting" && <p>Waiting for other participants...</p>}
      {status === "running" && info && (
        <div>
          <p>You are <b>{info.you}</b>. Participants: {info.players.join(", ")}</p>
          {phase && (
            <div>
              <h2>
                {PHASE_TITLES[phase.phase]}
                {phase.round ? ` (round ${phase.round})` : ""}
              </h2>
              {phase.phase !== "results" && <p>Time left: {secondsLeft}s</p>}
              {phase.phase === "results" && <p>The experiment is finished.</p>}
            </div>
          )}
        </div>
      )}
      {status === "closed" && <p style={{ color: "crimson" }}>Connection closed.</p>}
      <details style={{ marginTop: 24 }}>
        <summary>Last message (debug)</summary>
        <pre>{JSON.stringify(lastMsg, null, 2)}</pre>
      </details>
    </div>
  );
}