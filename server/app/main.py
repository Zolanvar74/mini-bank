import asyncio
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from server.app.core.audit_logger import write_audit_log
from server.app.core.config import settings
from server.app.database import initialize_database
from server.app.models import TransactionRequest
from server.app.services.banking_service import (
    AccountNotFoundError,
    InsufficientFundsError,
    InvalidAmountError,
    MissingAmountError,
    RequestIdConflictError,
    SimulatedFailureError,
    deposit,
    get_balance,
    withdraw,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()

    app.state.client_semaphore = asyncio.Semaphore(
        settings.max_clients
    )

    yield


app = FastAPI(
    title="Mini Banking Transaction Server",
    version="0.4.0",
    lifespan=lifespan,
)


def error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
):
    request.state.result = code

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "error",
            "code": code,
            "message": message,
        },
    )


@app.middleware("http")
async def limit_concurrent_clients(
    request: Request,
    call_next,
):
    semaphore = request.app.state.client_semaphore

    async with semaphore:
        return await call_next(request)


@app.middleware("http")
async def audit_requests(
    request: Request,
    call_next,
):
    started_at = time.perf_counter()

    timestamp = (
        datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )

    request.state.request_id = str(uuid.uuid4())
    request.state.action = None
    request.state.account = None
    request.state.result = None

    client_ip = (
        request.client.host
        if request.client
        else "unknown"
    )

    response = None

    try:
        response = await call_next(request)

        if request.state.result is None:
            request.state.result = (
                f"HTTP_{response.status_code}"
            )

        return response

    except Exception:
        request.state.result = "INTERNAL_ERROR"
        raise

    finally:
        latency_ms = round(
            (time.perf_counter() - started_at) * 1000,
            3,
        )

        status_code = (
            response.status_code
            if response is not None
            else 500
        )

        entry = {
            "timestamp": timestamp,
            "request_id": request.state.request_id,
            "client_ip": client_ip,
            "method": request.method,
            "path": request.url.path,
            "action": request.state.action,
            "account": request.state.account,
            "result": request.state.result,
            "status_code": status_code,
            "latency_ms": latency_ms,
        }

        try:
            write_audit_log(entry)
        except Exception as log_error:
            print(
                f"AUDIT_LOG_ERROR: {log_error}"
            )


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "banking-server",
    }


@app.post("/api/transaction")
def transaction(
    payload: TransactionRequest,
    request: Request,
):
    request.state.action = payload.action
    request.state.account = payload.account

    if payload.request_id is not None:
        request.state.request_id = payload.request_id

    if payload.account is None:
        return error_response(
            request=request,
            status_code=400,
            code="MISSING_FIELD",
            message="Field 'account' is required.",
        )

    if payload.action == "balance":
        try:
            current_balance = get_balance(
                payload.account
            )

            request.state.result = "success"

            return {
                "status": "success",
                "account": payload.account,
                "balance": current_balance,
            }

        except AccountNotFoundError:
            return error_response(
                request=request,
                status_code=404,
                code="UNKNOWN_ACCOUNT",
                message=(
                    f"Account {payload.account} "
                    "does not exist."
                ),
            )

    if payload.action == "deposit":
        if payload.request_id is None:
            return error_response(
                request=request,
                status_code=400,
                code="MISSING_FIELD",
                message=(
                    "Field 'request_id' is required."
                ),
            )

        try:
            response = deposit(
                request_id=payload.request_id,
                account_id=payload.account,
                amount=payload.amount,
                fail_after_update=(
                    settings.enable_fault_injection
                    and payload.failpoint
                    == "after_update"
                ),
            )

            request.state.result = "success"
            return response

        except MissingAmountError:
            return error_response(
                request,
                400,
                "MISSING_FIELD",
                "Field 'amount' is required.",
            )

        except InvalidAmountError:
            return error_response(
                request,
                400,
                "INVALID_AMOUNT",
                "Amount must be a positive integer.",
            )

        except AccountNotFoundError:
            return error_response(
                request,
                404,
                "UNKNOWN_ACCOUNT",
                (
                    f"Account {payload.account} "
                    "does not exist."
                ),
            )

        except RequestIdConflictError:
            return error_response(
                request,
                409,
                "REQUEST_ID_CONFLICT",
                (
                    "This request_id was already used "
                    "for a different transaction."
                ),
            )

        except SimulatedFailureError:
            return error_response(
                request,
                500,
                "SIMULATED_FAILURE",
                (
                    "A simulated failure occurred "
                    "before transaction commit."
                ),
            )

    if payload.action == "withdraw":
        if payload.request_id is None:
            return error_response(
                request,
                400,
                "MISSING_FIELD",
                "Field 'request_id' is required.",
            )

        try:
            response = withdraw(
                request_id=payload.request_id,
                account_id=payload.account,
                amount=payload.amount,
                fail_after_update=(
                    settings.enable_fault_injection
                    and payload.failpoint
                    == "after_update"
                ),
            )

            request.state.result = "success"
            return response

        except MissingAmountError:
            return error_response(
                request,
                400,
                "MISSING_FIELD",
                "Field 'amount' is required.",
            )

        except InvalidAmountError:
            return error_response(
                request,
                400,
                "INVALID_AMOUNT",
                "Amount must be a positive integer.",
            )

        except InsufficientFundsError:
            return error_response(
                request,
                409,
                "INSUFFICIENT_FUNDS",
                "Account balance is insufficient.",
            )

        except AccountNotFoundError:
            return error_response(
                request,
                404,
                "UNKNOWN_ACCOUNT",
                (
                    f"Account {payload.account} "
                    "does not exist."
                ),
            )

        except RequestIdConflictError:
            return error_response(
                request,
                409,
                "REQUEST_ID_CONFLICT",
                (
                    "This request_id was already used "
                    "for a different transaction."
                ),
            )

        except SimulatedFailureError:
            return error_response(
                request,
                500,
                "SIMULATED_FAILURE",
                (
                    "A simulated failure occurred "
                    "before transaction commit."
                ),
            )

    return error_response(
        request,
        400,
        "UNSUPPORTED_ACTION",
        f"Action '{payload.action}' is not supported.",
    )