from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from server.app.database import initialize_database
from server.app.models import TransactionRequest
from server.app.services.banking_service import (
    AccountNotFoundError,
    get_balance,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="Mini Banking Transaction Server",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "banking-server",
    }


@app.post("/api/transaction")
def transaction(request: TransactionRequest):
    if request.action == "balance":
        try:
            balance = get_balance(request.account)

            return {
                "status": "success",
                "account": request.account,
                "balance": balance,
            }

        except AccountNotFoundError:
            return JSONResponse(
                status_code=404,
                content={
                    "status": "error",
                    "code": "UNKNOWN_ACCOUNT",
                    "message": f"Account {request.account} does not exist.",
                },
            )

    return JSONResponse(
        status_code=400,
        content={
            "status": "error",
            "code": "NOT_IMPLEMENTED",
            "message": f"Action {request.action} is not implemented yet.",
        },
    )