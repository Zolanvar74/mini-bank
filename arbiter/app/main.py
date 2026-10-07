import time
from contextlib import asynccontextmanager

from fastapi import FastAPI

from arbiter.app.config import settings
from arbiter.app.database import (
    get_cluster_state,
    initialize_database,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="Mini Bank Arbiter",
    lifespan=lifespan,
)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "arbiter",
        "node_id": settings.node_id,
    }


@app.get("/cluster/status")
def cluster_status():
    state = get_cluster_state()

    lease_expires_at = state["lease_expires_at"]

    lease_valid = (
        lease_expires_at is not None
        and lease_expires_at > time.time()
    )

    return {
        "leader_id": state["leader_id"],
        "epoch": state["epoch"],
        "lease_expires_at": lease_expires_at,
        "lease_valid": lease_valid,
    }