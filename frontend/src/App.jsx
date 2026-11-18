import { useEffect, useRef, useState } from "react";

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
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [lastMsg, setLastMsg] = useState(null);
  const wsRef = useRef(null);
  const chatEndRef = useRef(null);

  useEffect(() => {
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(
      `${protocol}://${window.location.host}/ws/session?pid=${getPid()}`
    );
    wsRef.current = ws;
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
      if (msg.type === "history") setMessages(msg.messages);
      if (msg.type === "message") setMessages((prev) => [...prev, msg]);
    };
    ws.onclose = () => setStatus("closed");
    return () => ws.close();
  }, []);

  // Tick every 250 ms so the countdown stays smooth
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(t);
  }, []);

  // Keep the newest message in view
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const secondsLeft = Math.max(0, Math.ceil((endsAt - now) / 1000));
  const canChat = status === "running" && phase?.phase === "discuss";

  function send(e) {
    e.preventDefault();
    const text = draft.trim();
    if (!text || !canChat) return;
    wsRef.current.send(JSON.stringify({ type: "chat", text }));
    setDraft("");
  }

  return (
    <div style={{ fontFamily: "sans-serif", padding: 24, maxWidth: 600 }}>
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

          <div
            style={{
              border: "1px solid #ccc",
              borderRadius: 6,
              height: 220,
              overflowY: "auto",
              padding: 8,
              marginBottom: 8,
            }}
          >
            {messages.length === 0 && <p style={{ color: "#888" }}>No messages yet.</p>}
            {messages.map((m, i) => (
              <div key={i}>
                <b>{m.from === info.you ? `${m.from} (you)` : m.from}:</b> {m.text}
              </div>
            ))}
            <div ref={chatEndRef} />
          </div>

          <form onSubmit={send} style={{ display: "flex", gap: 8 }}>
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              disabled={!canChat}
              maxLength={300}
              placeholder={canChat ? "Type a message..." : "Chat is closed"}
              style={{ flex: 1, padding: 6 }}
            />
            <button type="submit" disabled={!canChat}>Send</button>
          </form>
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