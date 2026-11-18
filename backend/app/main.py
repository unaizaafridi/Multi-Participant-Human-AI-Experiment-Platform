import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pymongo import AsyncMongoClient

from .config import load_config


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.config = load_config()
    app.state.mongo = AsyncMongoClient(os.environ["MONGO_URL"])
    app.state.db = app.state.mongo["experiment"]
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


# Temporary test endpoint: removed once the real session WebSocket exists.
@app.websocket("/ws/echo")
async def ws_echo(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            text = await websocket.receive_text()
            await websocket.send_text(f"echo: {text}")
    except WebSocketDisconnect:
        pass