import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pymongo import AsyncMongoClient

from .config import load_config
from .session import SessionManager


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.config = load_config()
    app.state.mongo = AsyncMongoClient(os.environ["MONGO_URL"])
    app.state.db = app.state.mongo["experiment"]
    app.state.sessions = SessionManager(app.state.config, app.state.db)
    yield
    await app.state.mongo.close()


app = FastAPI(lifespan=lifespan)


@app.get("/api/health")
async def health():
    await app.state.mongo.admin.command("ping")
    participants = app.state.config["session"]["participants"]
    return {
        "status": "ok",
        "mongo": "ok",
        "human_slots": participants.count("human"),
        "ai_slots": participants.count("ai"),
    }


@app.websocket("/ws/session")
async def ws_session(websocket: WebSocket, pid: str):
    manager: SessionManager = app.state.sessions
    await manager.connect(pid, websocket)
    try:
        while True:
            await websocket.receive_text()  # client messages handled from Step 6
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(pid, websocket)