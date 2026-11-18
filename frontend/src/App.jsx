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

function Tally({ tally }) {
  return (
    <ul>
      {Object.entries(tally).map(([label, count]) => (
        <li key={label}>
          {label}: {count} vote{count === 1 ? "" : "s"}
        </li>
      ))}
    </ul>
  );
}

export default function App() {
  const [status, setStatus] = useState("connecting"); // connecting | waiting | running | closed
  const [info, setInfo] = useState(null);             // { you, players }
  const [phase, setPhase] = useState(null);           // last state_changed message
  const [endsAt, setEndsAt] = useState(0);            // local time when the phase ends
  const [now, setNow] = useState(Date.now());
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [myVote, setMyVote] = useState(null);         // { round, target }
  const [roundResults, setRoundResults] = useState([]);
  const [result, setResult] = useState(null);
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
      if (msg.type === "vote_ack") setMyVote({ round: msg.round, target: msg.target });
      if (msg.type === "round_result") {
        // replace if the same round arrives again after a reconnect
        setRoundResults((prev) => [...prev.filter((r) => r.round !== msg.round), msg]);
      }
      if (msg.type === "results") setResult(msg);
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
  const canVote = status === "running" && phase?.phase === "vote";
  const currentVote = myVote && myVote.round === phase?.round ? myVote.target : null;

  function send(e) {
    e.preventDefault();
    const text = draft.trim();
    if (!text || !canChat) return;
    wsRef.current.send(JSON.stringify({ type: "chat", text }));
    setDraft("");
  }

  function vote(target) {
    if (!canVote) return;
    wsRef.current.send(JSON.stringify({ type: "vote", target }));
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
            </div>
          )}

          {roundResults.map((r) => (
            <div key={r.round} style={{ background: "#f4f4f4", padding: 8, marginBottom: 8 }}>
              <b>Round {r.round} vote counts</b>
              <Tally tally={r.tally} />
            </div>
          ))}

          {canVote && (
            <div style={{ marginBottom: 12 }}>
              <p>Who should be the Decision Maker?</p>
              {info.players.map((label) => (
                <button
                  key={label}
                  onClick={() => vote(label)}
                  style={{
                    marginRight: 8,
                    padding: "6px 12px",
                    fontWeight: currentVote === label ? "bold" : "normal",
                    border: currentVote === label ? "2px solid #2563eb" : "1px solid #888",
                  }}
                >
                  {label}
                  {label === info.you ? " (you)" : ""}
                </button>
              ))}
              <p style={{ color: "#555" }}>
                {currentVote
                  ? `Your vote: ${currentVote}. You can change it until time runs out.`
                  : "You have not voted yet."}
              </p>
            </div>
          )}

          {phase?.phase === "results" && (
            <div style={{ border: "2px solid #16a34a", borderRadius: 6, padding: 12, marginBottom: 12 }}>
              {result ? (
                <>
                  <h2 style={{ marginTop: 0 }}>Decision Maker: {result.winner}</h2>
                  <Tally tally={result.tally} />
                  {result.tie_broken && <p style={{ color: "#555" }}>The vote was tied and the tie was broken.</p>}
                </>
              ) : (
                <p>The experiment is finished.</p>
              )}
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