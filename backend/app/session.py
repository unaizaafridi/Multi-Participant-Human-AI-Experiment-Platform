import asyncio
import random
import uuid
from datetime import datetime, timezone

from fastapi import WebSocket

LABELS = ["Player A", "Player B", "Player C"]


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
        self.created_at = datetime.now(timezone.utc)
        labels = LABELS[:]
        random.shuffle(labels)
        # Shuffled labels zipped with the configured types -> random seat per type
        self.participants = [Participant(l, t) for l, t in zip(labels, participant_types)]

    def humans(self) -> list[Participant]:
        return [p for p in self.participants if p.type == "human"]

    def free_human_slot(self) -> Participant | None:
        return next((p for p in self.humans() if p.pid is None), None)

    def is_full(self) -> bool:
        return self.free_human_slot() is None

    def labels(self) -> list[str]:
        return sorted(p.label for p in self.participants)

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

    # ---- internals ----

    async def _start(self, session: Session):
        session.state = "STARTED"  # placeholder, the real state machine comes in Step 5
        await self.db.sessions.insert_one(session.to_doc())
        for p in session.humans():
            await self._send_state(session, p)

    async def _send_state(self, session: Session, p: Participant):
        if p.ws is None:
            return
        if session.state == "WAITING":
            await p.ws.send_json({"type": "waiting"})
        else:
            # Only labels are sent. Participant types are never included.
            await p.ws.send_json({
                "type": "session_started",
                "you": p.label,
                "players": session.labels(),
            })