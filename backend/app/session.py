import asyncio
import logging
import random
import uuid
from datetime import datetime, timezone

from fastapi import WebSocket

from .agents import make_provider

log = logging.getLogger("session")

LABELS = ["Player A", "Player B", "Player C"]
MAX_MESSAGE_LENGTH = 300


class Participant:
    def __init__(self, label: str, ptype: str):
        self.label = label
        self.type = ptype      # "human" | "ai" (internal only, never sent to clients)
        self.pid: str | None = None
        self.ws: WebSocket | None = None
        self.provider = None   # AI behaviour, only set for ai participants


class Session:
    def __init__(self, participant_types: list[str]):
        self.id = uuid.uuid4().hex[:8]
        self.state = "WAITING"
        self.phase: str | None = None        # "discuss" | "vote" | "closing" | "results"
        self.round: int | None = None
        self.phase_ends_at: float = 0.0      # event-loop time when the phase ends
        self.messages: list[dict] = []       # public chat history (labels only)
        self.votes: dict[int, dict[str, str]] = {}   # round -> {voter label: target label}
        self.round_feedback: list[dict] = []         # round_result messages already sent
        self.result: dict | None = None              # final result, set after the last vote
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

    def _spawn(self, coro):
        task = asyncio.create_task(coro)
        self.tasks.add(task)  # keep a reference so the task isn't garbage collected
        task.add_done_callback(self.tasks.discard)

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
            kind = data.get("type")
            if kind == "chat":
                await self._post_message(session, p, data.get("text"))
            elif kind == "vote":
                await self._cast_vote(session, p, data.get("target"))

    async def _post_message(self, session: Session, p: Participant, text):
        """Shared by humans and AI agents."""
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

    async def _cast_vote(self, session: Session, p: Participant, target):
        """Shared by humans and AI agents. The last vote in a round counts."""
        if session.phase != "vote":
            return
        if not isinstance(target, str) or target not in session.labels():
            return
        session.votes.setdefault(session.round, {})[p.label] = target
        await self.db.votes.update_one(
            {"session_id": session.id, "round": session.round, "voter": p.label},
            {"$set": {
                "voter_type": p.type,   # internal only, never sent to clients
                "target": target,
                "updated_at": datetime.now(timezone.utc),
            }},
            upsert=True,
        )
        await self._send_json(p, {"type": "vote_ack", "round": session.round, "target": target})

    # ---- AI agents ----

    def _agent_context(self, session: Session, p: Participant) -> dict:
        """Only public information, the same a human player can see."""
        return {
            "you": p.label,
            "players": session.labels(),
            "round": session.round,
            "messages": list(session.messages),
            "round1_tally": self._tally(session, 1) if (session.round or 0) > 1 else None,
        }

    async def _agent_phase(self, session: Session, p: Participant, state: str):
        """Runs one AI agent for one phase. Ends when the phase changes."""
        ai = self.config["ai"]
        try:
            if state.endswith("_DISCUSS"):
                while session.state == state:
                    await asyncio.sleep(
                        random.uniform(ai["min_delay_seconds"], ai["max_delay_seconds"])
                    )
                    if session.state != state:
                        return
                    text = await p.provider.generate_message(self._agent_context(session, p))
                    if not text:
                        continue
                    await asyncio.sleep(min(3.0, len(text) * 0.05))  # "typing" time
                    if session.state != state:
                        return
                    async with self.lock:
                        await self._post_message(session, p, text)
            elif state.endswith("_VOTE"):
                left = session.seconds_left()
                await asyncio.sleep(random.uniform(min(2, left * 0.3), max(0.5, left * 0.7)))
                if session.state != state:
                    return
                target = await p.provider.decide_vote(self._agent_context(session, p))
                async with self.lock:
                    await self._cast_vote(session, p, target)
        except Exception:
            log.exception("AI agent %s failed in %s", p.label, state)

    # ---- counting ----

    def _tally(self, session: Session, rnd: int) -> dict[str, int]:
        tally = {label: 0 for label in session.labels()}
        for target in session.votes.get(rnd, {}).values():
            tally[target] += 1
        return tally

    def _decide(self, session: Session, tally: dict[str, int]) -> dict:
        top = max(tally.values())
        candidates = [label for label, count in tally.items() if count == top]
        tie = len(candidates) > 1

        if tie and self.config["results"]["tie_break"] == "round1":
            r1 = self._tally(session, 1)
            best = max(r1[label] for label in candidates)
            candidates = [label for label in candidates if r1[label] == best]

        winner = random.choice(candidates)  # only random if still tied
        return {"winner": winner, "tally": tally, "tie_broken": tie}

    async def _finish_round(self, session: Session, rnd: int):
        tally = self._tally(session, rnd)
        if rnd == self.config["session"]["rounds"]:
            session.result = self._decide(session, tally)
            await self.db.sessions.update_one(
                {"_id": session.id}, {"$set": {"result": session.result}}
            )
        elif self.config["results"]["round1_feedback"] == "tally":
            msg = {"type": "round_result", "round": rnd, "tally": tally}
            session.round_feedback.append(msg)
            await self._broadcast(session, msg)

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
        for p in session.participants:
            if p.type == "ai":
                p.provider = make_provider(self.config)
        await self.db.sessions.insert_one(session.to_doc())
        for p in session.humans():
            await self._send_json(p, self._started_msg(session, p))
        self._spawn(self._run(session))

    async def _run(self, session: Session):
        loop = asyncio.get_running_loop()
        for state, rnd, phase, duration in self._build_phases():
            session.state, session.round, session.phase = state, rnd, phase
            session.phase_ends_at = loop.time() + duration
            await self.db.sessions.update_one({"_id": session.id}, {"$set": {"state": state}})
            await self._broadcast(session, self._phase_msg(session))
            if phase == "results" and session.result:
                await self._broadcast(session, self._results_msg(session))
            if phase in ("discuss", "vote"):
                for p in session.participants:
                    if p.type == "ai":
                        self._spawn(self._agent_phase(session, p, state))
            if duration:
                await asyncio.sleep(duration)
                async with self.lock:
                    session.phase = "closing"  # no more chat or votes accepted
                    if phase == "vote":
                        await self._finish_round(session, rnd)

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

    def _results_msg(self, session: Session) -> dict:
        return {"type": "results", **session.result}

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
        for msg in session.round_feedback:
            await self._send_json(p, msg)
        if session.phase == "vote":
            current = session.votes.get(session.round, {}).get(p.label)
            if current:
                await self._send_json(
                    p, {"type": "vote_ack", "round": session.round, "target": current}
                )
        if session.phase == "results" and session.result:
            await self._send_json(p, self._results_msg(session))