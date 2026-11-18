import asyncio
import random
import uuid
from datetime import datetime, timezone

from fastapi import WebSocket

LABELS = ["Player A", "Player B", "Player C"]
MAX_MESSAGE_LENGTH = 300


class Participant:
    def __init__(self, label: str, ptype: str):
        self.label = label
        self.type = ptype      # "human" | "ai" (internal only, never sent to clients)
        self.pid: str | None = None
        self.ws: WebSocket | None = None


class Session:
    def __init__(self, participant_types: list[str]):
        self.id = uuid.uuid4().hex[:8]
        self.state = "WAITING"
        self.phase: str | None = None        # "discuss" | "vote" | "results"
        self.round: int | None = None
        self.phase_ends_at: float = 0.0      # event-loop time when the phase ends
        self.messages: list[dict] = []       # public chat history (labels only)
        self.created_at = datetime.now(timezone.utc)
        labels = LABELS[:]
        random.shuffle(labels)
        self.participants = [Participant(l, t) for l, t in zip(labels, participant_types)]

    def humans(self) -> list[Participant]:
        return [p for p in self.participants if p.type == "human"]

    def free_human_slot(self) -> Participant | None:
        return next((p for p in self.humans() if p.pid is None), None)

    def is_full(self) -> bool:
        return self.free_human_slot() is None

    def labels(self) -> list[str]:
        return sorted(p.label for p in self.participants)

    def seconds_left(self) -> int:
        loop = asyncio.get_running_loop()
        return max(0, round(self.phase_ends_at - loop.time()))

    def to_doc(self) -> dict:
        return {
            "_id": self.id,
            "state": self.state,
            "created_at": self.created_at,
            "participants": [
                {"label": p.label, "type": p.type, "pid": p.pid}
                for p in self.participants
            ],
        }


class SessionManager:
    def __init__(self, config: dict, db):
        self.config = config
        self.db = db
        self.waiting: Session | None = None
        self.by_pid: dict[str, tuple[Session, Participant]] = {}
        self.lock = asyncio.Lock()
        self.tasks: set[asyncio.Task] = set()

    # ---- connection lifecycle ----

    async def connect(self, pid: str, ws: WebSocket):
        await ws.accept()
        async with self.lock:
            existing = self.by_pid.get(pid)
            if existing:  # reconnect (e.g. page refresh)
                session, p = existing
                p.ws = ws
                await self._send_state(session, p)
                return

            if self.waiting is None:
                self.waiting = Session(self.config["session"]["participants"])
            session = self.waiting

            p = session.free_human_slot()
            p.pid, p.ws = pid, ws
            self.by_pid[pid] = (session, p)

            if session.is_full():
                self.waiting = None
                await self._start(session)
            else:
                await ws.send_json({"type": "waiting"})

    async def disconnect(self, pid: str, ws: WebSocket):
        async with self.lock:
            entry = self.by_pid.get(pid)
            if not entry:
                return
            session, p = entry
            if p.ws is not ws:  # stale socket, a newer one already took over
                return
            p.ws = None
            if session.state == "WAITING":  # leave the waiting room, free the seat
                p.pid = None
                del self.by_pid[pid]

    # ---- incoming client messages ----

    async def handle(self, pid: str, data: dict):
        async with self.lock:
            entry = self.by_pid.get(pid)
            if not entry or not isinstance(data, dict):
                return
            session, p = entry
            if data.get("type") == "chat":
                await self._post_message(session, p, data.get("text"))
            # "vote" is handled from Step 7

    async def _post_message(self, session: Session, p: Participant, text):
        """Shared by humans (now) and AI agents (Step 8)."""
        if session.phase != "discuss":
            return
        if not isinstance(text, str):
            return
        text = text.strip()[:MAX_MESSAGE_LENGTH]
        if not text:
            return

        public = {"type": "message", "from": p.label, "text": text, "round": session.round}
        session.messages.append(public)
        await self.db.messages.insert_one({
            "session_id": session.id,
            "round": session.round,
            "label": p.label,
            "sender_type": p.type,   # internal only, never sent to clients
            "text": text,
            "created_at": datetime.now(timezone.utc),
        })
        await self._broadcast(session, public)

    # ---- state machine ----

    def _build_phases(self) -> list[tuple[str, int | None, str, int]]:
        """Returns (state_name, round, phase, duration_seconds) for every phase."""
        s = self.config["session"]
        phases = []
        for r in range(1, s["rounds"] + 1):
            phases.append((f"ROUND_{r}_DISCUSS", r, "discuss", s["discussion_seconds"]))
            phases.append((f"ROUND_{r}_VOTE", r, "vote", s["vote_seconds"]))
        phases.append(("RESULTS", None, "results", 0))
        return phases

    async def _start(self, session: Session):
        await self.db.sessions.insert_one(session.to_doc())
        for p in session.humans():
            await self._send_json(p, self._started_msg(session, p))
        task = asyncio.create_task(self._run(session))
        self.tasks.add(task)  # keep a reference so the task isn't garbage collected
        task.add_done_callback(self.tasks.discard)

    async def _run(self, session: Session):
        loop = asyncio.get_running_loop()
        for state, rnd, phase, duration in self._build_phases():
            session.state, session.round, session.phase = state, rnd, phase
            session.phase_ends_at = loop.time() + duration
            await self.db.sessions.update_one({"_id": session.id}, {"$set": {"state": state}})
            await self._broadcast(session, self._phase_msg(session))
            if duration:
                await asyncio.sleep(duration)

    # ---- messaging ----

    def _started_msg(self, session: Session, p: Participant) -> dict:
        # Only labels are sent. Participant types are never included.
        return {"type": "session_started", "you": p.label, "players": session.labels()}

    def _phase_msg(self, session: Session) -> dict:
        return {
            "type": "state_changed",
            "state": session.state,
            "phase": session.phase,
            "round": session.round,
            "seconds_left": session.seconds_left(),
        }

    async def _send_json(self, p: Participant, msg: dict):
        if p.ws is None:
            return
        try:
            await p.ws.send_json(msg)
        except Exception:
            p.ws = None  # dead socket, treated as disconnected

    async def _broadcast(self, session: Session, msg: dict):
        for p in session.humans():
            await self._send_json(p, msg)

    async def _send_state(self, session: Session, p: Participant):
        if session.state == "WAITING":
            await self._send_json(p, {"type": "waiting"})
            return
        await self._send_json(p, self._started_msg(session, p))
        await self._send_json(p, self._phase_msg(session))
        await self._send_json(p, {"type": "history", "messages": session.messages})