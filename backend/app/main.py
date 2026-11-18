import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
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