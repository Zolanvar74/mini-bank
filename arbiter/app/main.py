import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from arbiter.app.config import settings
from arbiter.app.database import (
    get_cluster_state,
    initialize_database,
)
from arbiter.app.models import (
    AcquireLeaseRequest,
    RenewLeaseRequest,
)
from arbiter.app.services import (
    LeaseHeldError,
    LeaseRenewalError,
    acquire_leadership,
    renew_leadership,
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


@app.post("/cluster/acquire")
def acquire_lease(payload: AcquireLeaseRequest):
    try:
        result = acquire_leadership(payload.node_id)

    except LeaseHeldError as exc:
        return JSONResponse(
            status_code=409,
            content={
                "status": "error",
                "code": "LEASE_HELD",
                "leader_id": exc.leader_id,
                "epoch": exc.epoch,
                "lease_expires_at": exc.lease_expires_at,
            },
        )

    return {
        "status": "success",
        "leader_id": result["leader_id"],
        "epoch": result["epoch"],
        "lease_expires_at": result["lease_expires_at"],
    }
    
@app.post("/cluster/renew")
def renew_lease(payload: RenewLeaseRequest):
    try:
        result = renew_leadership(
            node_id=payload.node_id,
            epoch=payload.epoch,
        )

    except LeaseRenewalError as exc:
        return JSONResponse(
            status_code=409,
            content={
                "status": "error",
                "code": exc.code,
                "leader_id": exc.leader_id,
                "epoch": exc.epoch,
                "lease_expires_at": exc.lease_expires_at,
            },
        )

    return {
        "status": "success",
        "leader_id": result["leader_id"],
        "epoch": result["epoch"],
        "lease_expires_at": result["lease_expires_at"],
    }