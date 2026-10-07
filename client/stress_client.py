import argparse
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx


def send_withdraw(
    base_url: str,
    account: str,
    amount: int,
):
    request_id = str(uuid.uuid4())

    payload = {
        "request_id": request_id,
        "action": "withdraw",
        "account": account,
        "amount": amount,
    }

    started_at = time.perf_counter()

    try:
        response = httpx.post(
            f"{base_url}/api/transaction",
            json=payload,
            timeout=30,
        )

        latency_ms = (
            time.perf_counter() - started_at
        ) * 1000

        return {
            "status_code": response.status_code,
            "body": response.json(),
            "latency_ms": latency_ms,
        }

    except Exception as exc:
        return {
            "status_code": 0,
            "body": {
                "status": "error",
                "message": str(exc),
            },
            "latency_ms": 0,
        }


def get_balance(base_url: str, account: str):
    response = httpx.post(
        f"{base_url}/api/transaction",
        json={
            "action": "balance",
            "account": account,
        },
        timeout=30,
    )

    return response.json()


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8000",
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

    args = parser.parse_args()

    print(
        f"Sending {args.requests} concurrent withdrawals..."
    )

    results = []

    started_at = time.perf_counter()

    with ThreadPoolExecutor(
        max_workers=args.workers
    ) as executor:
        futures = [
            executor.submit(
                send_withdraw,
                args.url,
                args.account,
                args.amount,
            )
            for _ in range(args.requests)
        ]

        for future in as_completed(futures):
            results.append(future.result())

    elapsed = time.perf_counter() - started_at

    success_count = 0
    insufficient_count = 0
    other_errors = 0

    for result in results:
        body = result["body"]

        if body.get("status") == "success":
            success_count += 1

        elif body.get("code") == "INSUFFICIENT_FUNDS":
            insufficient_count += 1

        else:
            other_errors += 1

    final_balance = get_balance(
        args.url,
        args.account,
    )

    print()
    print("=== Stress Test Result ===")
    print(f"Success:            {success_count}")
    print(f"Insufficient funds: {insufficient_count}")
    print(f"Other errors:       {other_errors}")
    print(f"Elapsed:            {elapsed:.2f}s")
    print(f"Final balance:      {final_balance}")


if __name__ == "__main__":
    main()