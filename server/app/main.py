from contextlib import asynccontextmanager
import asyncio
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from server.app.database import initialize_database
from server.app.models import TransactionRequest
from server.app.services.banking_service import (
    AccountNotFoundError,
    InsufficientFundsError,
    InvalidAmountError,
    MissingAmountError,
    RequestIdConflictError,
    deposit,
    get_balance,
    withdraw,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="Mini Banking Transaction Server",
    version="0.3.0",
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
    if request.account is None:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "code": "MISSING_FIELD",
                "message": "Field 'account' is required.",
            },
        )

    if request.action == "balance":
        try:
            current_balance = get_balance(request.account)

            return {
                "status": "success",
                "account": request.account,
                "balance": current_balance,
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

    if request.action == "deposit":
        if request.request_id is None:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "code": "MISSING_FIELD",
                    "message": "Field 'request_id' is required.",
                },
            )

        try:
            return deposit(
                request_id=request.request_id,
                account_id=request.account,
                amount=request.amount,
            )

        except MissingAmountError:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "code": "MISSING_FIELD",
                    "message": "Field 'amount' is required.",
                },
            )

        except InvalidAmountError:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "code": "INVALID_AMOUNT",
                    "message": "Amount must be a positive integer.",
                },
            )

        except AccountNotFoundError:
            return JSONResponse(
                status_code=404,
                content={
                    "status": "error",
                    "code": "UNKNOWN_ACCOUNT",
                    "message": f"Account {request.account} does not exist.",
                },
            )

        except RequestIdConflictError:
            return JSONResponse(
                status_code=409,
                content={
                    "status": "error",
                    "code": "REQUEST_ID_CONFLICT",
                    "message": (
                        "This request_id was already used "
                        "for a different transaction."
                    ),
                },
            )

    if request.action == "withdraw":
        if request.request_id is None:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "code": "MISSING_FIELD",
                    "message": "Field 'request_id' is required.",
                },
            )

        try:
            return withdraw(
                request_id=request.request_id,
                account_id=request.account,
                amount=request.amount,
            )

        except MissingAmountError:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "code": "MISSING_FIELD",
                    "message": "Field 'amount' is required.",
                },
            )

        except InvalidAmountError:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "code": "INVALID_AMOUNT",
                    "message": "Amount must be a positive integer.",
                },
            )

        except InsufficientFundsError:
            return JSONResponse(
                status_code=409,
                content={
                    "status": "error",
                    "code": "INSUFFICIENT_FUNDS",
                    "message": "Account balance is insufficient.",
                },
            )

        except AccountNotFoundError:
            return JSONResponse(
                status_code=404,
                content={
                    "status": "error",
                    "code": "UNKNOWN_ACCOUNT",
                    "message": f"Account {request.account} does not exist.",
                },
            )

        except RequestIdConflictError:
            return JSONResponse(
                status_code=409,
                content={
                    "status": "error",
                    "code": "REQUEST_ID_CONFLICT",
                    "message": (
                        "This request_id was already used "
                        "for a different transaction."
                    ),
                },
            )

    return JSONResponse(
        status_code=400,
        content={
            "status": "error",
            "code": "UNSUPPORTED_ACTION",
            "message": f"Action '{request.action}' is not supported.",
        },
    )