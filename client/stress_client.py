import argparse
import time
import uuid
from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed,
)

import httpx


RETRYABLE_CODES = {
    "NOT_PRIMARY",
    "REPLICATION_UNAVAILABLE",
    "ARBITER_UNAVAILABLE",
    "STALE_EPOCH",
    "NOT_LEADER",
    "LEASE_EXPIRED",
}


def transaction_url(base_url: str) -> str:
    return (
        base_url.rstrip("/")
        + "/api/transaction"
    )


def cluster_status_url(base_url: str) -> str:
    return (
        base_url.rstrip("/")
        + "/cluster/local-status"
    )


def send_transaction_with_failover(
    *,
    base_urls: list[str],
    payload: dict,
    failover_timeout: float = 15.0,
    retry_delay: float = 0.25,
    request_timeout: float = 2.0,
) -> dict:
    if not base_urls:
        raise ValueError(
            "At least one server URL is required."
        )

    started_at = time.monotonic()
    attempts = 0
    last_error = None

    while True:
        for base_url in base_urls:
            attempts += 1

            try:
                response = httpx.post(
                    transaction_url(base_url),
                    json=payload,
                    timeout=request_timeout,
                )

            except httpx.RequestError as exc:
                last_error = {
                    "server": base_url,
                    "type": "connection_error",
                    "message": str(exc),
                }
                continue

            try:
                body = response.json()

            except ValueError:
                last_error = {
                    "server": base_url,
                    "type": "invalid_response",
                    "status_code": (
                        response.status_code
                    ),
                }
                continue

            result = {
                "status_code": (
                    response.status_code
                ),
                "body": body,
                "server": base_url,
                "attempts": attempts,
            }

            if body.get("status") == "success":
                return result

            code = body.get("code")

            if code in RETRYABLE_CODES:
                last_error = {
                    "server": base_url,
                    "type": "retryable_error",
                    "status_code": (
                        response.status_code
                    ),
                    "code": code,
                }
                continue

            # Business errors such as
            # INSUFFICIENT_FUNDS are final.
            return result

        elapsed = (
            time.monotonic() - started_at
        )

        if elapsed >= failover_timeout:
            return {
                "status_code": 0,
                "body": {
                    "status": "error",
                    "code": "FAILOVER_TIMEOUT",
                    "message": (
                        "No writable primary became "
                        "available before the "
                        "failover timeout."
                    ),
                    "last_error": last_error,
                },
                "server": None,
                "attempts": attempts,
            }

        time.sleep(retry_delay)


def send_withdraw(
    *,
    base_urls: list[str],
    account: str,
    amount: int,
    failover_timeout: float,
    retry_delay: float,
    request_timeout: float,
) -> dict:
    # This request_id is created ONCE.
    # Every retry on A or B uses the same ID.
    request_id = str(uuid.uuid4())

    payload = {
        "request_id": request_id,
        "action": "withdraw",
        "account": account,
        "amount": amount,
    }

    started_at = time.perf_counter()

    result = send_transaction_with_failover(
        base_urls=base_urls,
        payload=payload,
        failover_timeout=failover_timeout,
        retry_delay=retry_delay,
        request_timeout=request_timeout,
    )

    result["latency_ms"] = (
        time.perf_counter() - started_at
    ) * 1000

    result["request_id"] = request_id

    return result


def find_primary(
    *,
    base_urls: list[str],
    request_timeout: float = 2.0,
) -> str | None:
    for base_url in base_urls:
        try:
            response = httpx.get(
                cluster_status_url(base_url),
                timeout=request_timeout,
            )

            if response.status_code != 200:
                continue

            body = response.json()

        except (
            httpx.RequestError,
            ValueError,
        ):
            continue

        if (
            body.get("role") == "PRIMARY"
            and body.get("lease_valid") is True
        ):
            return base_url

    return None


def get_balance(
    *,
    base_urls: list[str],
    account: str,
    request_timeout: float = 2.0,
) -> dict:
    primary_url = find_primary(
        base_urls=base_urls,
        request_timeout=request_timeout,
    )

    if primary_url is None:
        return {
            "status": "error",
            "code": "NO_PRIMARY",
            "message": (
                "Could not find an active primary "
                "for the final balance query."
            ),
        }

    try:
        response = httpx.post(
            transaction_url(primary_url),
            json={
                "action": "balance",
                "account": account,
            },
            timeout=request_timeout,
        )

        return response.json()

    except httpx.RequestError as exc:
        return {
            "status": "error",
            "code": "BALANCE_REQUEST_FAILED",
            "message": str(exc),
        }

    except ValueError:
        return {
            "status": "error",
            "code": "INVALID_BALANCE_RESPONSE",
        }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Failover-aware Mini Bank "
            "stress client."
        )
    )

    parser.add_argument(
        "--urls",
        nargs="+",
        default=[
            "http://192.168.111.128:8000",
            "http://192.168.111.129:8000",
        ],
        help=(
            "Ordered list of banking server URLs."
        ),
    )

    parser.add_argument(
        "--account",
        default="A1001",
    )

    parser.add_argument(
        "--amount",
        type=int,
        default=10,
    )

    parser.add_argument(
        "--requests",
        type=int,
        default=120,
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=20,
    )

    parser.add_argument(
        "--failover-timeout",
        type=float,
        default=15.0,
        help=(
            "Maximum seconds a transaction may "
            "wait for a writable primary."
        ),
    )

    parser.add_argument(
        "--retry-delay",
        type=float,
        default=0.25,
    )

    parser.add_argument(
        "--request-timeout",
        type=float,
        default=2.0,
    )

    args = parser.parse_args()

    print(
        f"Sending {args.requests} concurrent "
        f"withdrawals..."
    )

    print("Servers:")

    for server in args.urls:
        print(f"  - {server}")

    results = []

    started_at = time.perf_counter()

    with ThreadPoolExecutor(
        max_workers=args.workers
    ) as executor:
        futures = [
            executor.submit(
                send_withdraw,
                base_urls=args.urls,
                account=args.account,
                amount=args.amount,
                failover_timeout=(
                    args.failover_timeout
                ),
                retry_delay=args.retry_delay,
                request_timeout=(
                    args.request_timeout
                ),
            )
            for _ in range(args.requests)
        ]

        for future in as_completed(futures):
            results.append(
                future.result()
            )

    elapsed = (
        time.perf_counter() - started_at
    )

    success_count = 0
    insufficient_count = 0
    failover_timeout_count = 0
    other_errors = 0

    served_by = {}

    total_attempts = 0

    for result in results:
        body = result["body"]

        total_attempts += result.get(
            "attempts",
            0,
        )

        server = result.get("server")

        if server is not None:
            served_by[server] = (
                served_by.get(server, 0) + 1
            )

        if body.get("status") == "success":
            success_count += 1

        elif (
            body.get("code")
            == "INSUFFICIENT_FUNDS"
        ):
            insufficient_count += 1

        elif (
            body.get("code")
            == "FAILOVER_TIMEOUT"
        ):
            failover_timeout_count += 1

        else:
            other_errors += 1

    final_balance = get_balance(
        base_urls=args.urls,
        account=args.account,
        request_timeout=args.request_timeout,
    )

    print()
    print("=== Stress Test Result ===")

    print(
        f"Success:             "
        f"{success_count}"
    )

    print(
        f"Insufficient funds:  "
        f"{insufficient_count}"
    )

    print(
        f"Failover timeouts:   "
        f"{failover_timeout_count}"
    )

    print(
        f"Other errors:        "
        f"{other_errors}"
    )

    print(
        f"Total attempts:      "
        f"{total_attempts}"
    )

    print(
        f"Elapsed:             "
        f"{elapsed:.2f}s"
    )

    print(
        f"Final balance:       "
        f"{final_balance}"
    )

    print()
    print("=== Requests Served By ===")

    if not served_by:
        print("No successful server responses.")

    else:
        for server, count in served_by.items():
            print(
                f"{server}: {count}"
            )


if __name__ == "__main__":
    main()