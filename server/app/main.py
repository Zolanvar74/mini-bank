import asyncio
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone



from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from server.app.services.replica_service import (
    ReplicaApplyError,
    ReplicaGapError,
    sync_from_arbiter,
)
from server.app.core.wal_client import (
    ArbiterUnavailableError,
    WalRejectedError,
    commit_transaction_to_wal,
)
from server.app.core.cluster_manager import ClusterManager
from server.app.core.audit_logger import write_audit_log
from server.app.core.config import settings
from server.app.database import (
    get_last_seq,
    initialize_database,
)
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

    cluster_manager = ClusterManager()
    app.state.cluster_manager = cluster_manager

    await cluster_manager.start()

    try:
        yield
    finally:
        await cluster_manager.stop()


app = FastAPI(
    title="Mini Banking Transaction Server",
    version="0.4.0",
    lifespan=lifespan,
)

@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    errors = exc.errors()

    for error in errors:
        error_type = error.get("type")

        if error_type == "json_invalid":
            request.state.result = "MALFORMED_REQUEST"

            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "code": "MALFORMED_REQUEST",
                    "message": "Request body contains invalid JSON.",
                },
            )

    missing_fields = []

    for error in errors:
        if error.get("type") == "missing":
            location = error.get("loc", [])

            if location:
                missing_fields.append(
                    str(location[-1])
                )

    if missing_fields:
        request.state.result = "MISSING_FIELD"

        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "code": "MISSING_FIELD",
                "message": (
                    "Missing required field(s): "
                    + ", ".join(missing_fields)
                ),
            },
        )

    request.state.result = "INVALID_REQUEST"

    return JSONResponse(
        status_code=400,
        content={
            "status": "error",
            "code": "INVALID_REQUEST",
            "message": "Request validation failed.",
        },
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
    
    
class NotPrimaryError(Exception):
    pass


def get_write_epoch(request: Request) -> int | None:
    if not settings.cluster_enabled:
        return None

    context = (
        request.app.state.cluster_manager
        .write_context()
    )

    if (
        context["role"] != "PRIMARY"
        or not context["lease_valid"]
        or context["epoch"] is None
    ):
        raise NotPrimaryError()

    return context["epoch"]


def build_wal_commit_callback(
    request: Request,
    payload: TransactionRequest,
    action: str,
):
    epoch = get_write_epoch(request)

    if epoch is None:
        return None

    def wal_commit(
        response: dict,
        balance_after: int,
    ):
        return commit_transaction_to_wal(
            node_id=settings.node_id,
            epoch=epoch,
            request_id=payload.request_id,
            action=action,
            account_id=payload.account,
            amount=payload.amount,
            balance_after=balance_after,
            response_json=response,
        )

    return wal_commit


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

@app.get("/cluster/local-status")
async def local_cluster_status(request: Request):
    result = await (
        request.app.state.cluster_manager.snapshot()
    )

    result["last_seq"] = get_last_seq()

    return result


@app.post("/cluster/sync-now")
def cluster_sync_now(request: Request):
    context = (
        request.app.state.cluster_manager
        .write_context()
    )

    if context["role"] == "PRIMARY":
        return error_response(
            request,
            409,
            "PRIMARY_CANNOT_SYNC",
            (
                "An active primary cannot replay "
                "replica WAL."
            ),
        )

    try:
        result = sync_from_arbiter()

    except ArbiterUnavailableError:
        return error_response(
            request,
            503,
            "ARBITER_UNAVAILABLE",
            "Could not fetch WAL from Arbiter.",
        )

    except ReplicaGapError:
        return error_response(
            request,
            409,
            "WAL_GAP",
            (
                "Replica WAL sequence contains "
                "a gap."
            ),
        )

    except ReplicaApplyError:
        return error_response(
            request,
            409,
            "WAL_APPLY_FAILED",
            "Replica could not apply WAL.",
        )

    request.state.result = "success"

    return {
        "status": "success",
        **result,
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
            
            wal_commit = build_wal_commit_callback(
                request,
                payload,
                "deposit",
            )
            response = deposit(
                request_id=payload.request_id,
                account_id=payload.account,
                amount=payload.amount,
                fail_after_update=(
                    settings.enable_fault_injection
                    and payload.failpoint == "after_update"
                ),
                wal_commit=wal_commit,
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
        except NotPrimaryError:
            return error_response(
                request,
                503,
                "NOT_PRIMARY",
                "This server is not the active primary.",
            )

        except ArbiterUnavailableError:
            request.app.state.cluster_manager.fence_now(
                "WAL_COMMIT_UNCERTAIN"
            )

            return error_response(
                request,
                503,
                "REPLICATION_UNAVAILABLE",
                (
                    "The transaction could not be "
                    "durably confirmed by the Arbiter."
                ),
            )

        except WalRejectedError as exc:
            request.app.state.cluster_manager.fence_now(
                exc.code
            )

            return error_response(
                request,
                503,
                exc.code,
                "The cluster rejected this write.",
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
            wal_commit = build_wal_commit_callback(
                request,
                payload,
                "withdraw",
            )
            response = withdraw(
                request_id=payload.request_id,
                account_id=payload.account,
                amount=payload.amount,
                fail_after_update=(
                    settings.enable_fault_injection
                    and payload.failpoint == "after_update"
                ),
                wal_commit=wal_commit,
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
            
        except NotPrimaryError:
            return error_response(
                request,
                503,
                "NOT_PRIMARY",
                "This server is not the active primary.",
            )

        except ArbiterUnavailableError:
            request.app.state.cluster_manager.fence_now(
                "WAL_COMMIT_UNCERTAIN"
            )

            return error_response(
                request,
                503,
                "REPLICATION_UNAVAILABLE",
                (
                    "The transaction could not be "
                    "durably confirmed by the Arbiter."
                ),
            )

        except WalRejectedError as exc:
            request.app.state.cluster_manager.fence_now(
                exc.code
            )

            return error_response(
                request,
                503,
                exc.code,
                "The cluster rejected this write.",
            )

    return error_response(
        request,
        400,
        "UNSUPPORTED_ACTION",
        f"Action '{payload.action}' is not supported.",
    )