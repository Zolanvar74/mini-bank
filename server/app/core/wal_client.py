import httpx

from server.app.core.config import settings


class ArbiterUnavailableError(Exception):
    pass


class WalRejectedError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def commit_transaction_to_wal(
    *,
    node_id: str,
    epoch: int,
    request_id: str,
    action: str,
    account_id: str,
    amount: int,
    balance_after: int,
    response_json: dict,
) -> dict:

    payload = {
        "node_id": node_id,
        "epoch": epoch,
        "request_id": request_id,
        "action": action,
        "account_id": account_id,
        "amount": amount,
        "status": "success",
        "balance_after": balance_after,
        "response_json": response_json,
    }

    try:
        response = httpx.post(
            f"{settings.arbiter_url}/wal/commit",
            json=payload,
            timeout=settings.cluster_request_timeout_seconds,
        )

    except httpx.RequestError as exc:
        raise ArbiterUnavailableError(
            "Arbiter could not confirm WAL commit."
        ) from exc

    try:
        body = response.json()
    except ValueError as exc:
        raise ArbiterUnavailableError(
            "Arbiter returned invalid JSON."
        ) from exc

    if response.status_code == 200:
        if not isinstance(body.get("seq"), int):
            raise ArbiterUnavailableError(
                "Arbiter returned invalid WAL sequence."
            )

        return body

    if response.status_code == 409:
        raise WalRejectedError(
            body.get("code", "WAL_REJECTED")
        )

    raise ArbiterUnavailableError(
        f"Unexpected Arbiter response: "
        f"HTTP {response.status_code}"
    )
    
def fetch_wal_since(seq: int) -> list[dict]:
    try:
        response = httpx.get(
            f"{settings.arbiter_url}/wal/since/{seq}",
            timeout=settings.cluster_request_timeout_seconds,
        )

    except httpx.RequestError as exc:
        raise ArbiterUnavailableError(
            "Could not fetch WAL from Arbiter."
        ) from exc

    try:
        body = response.json()
    except ValueError as exc:
        raise ArbiterUnavailableError(
            "Arbiter returned invalid JSON."
        ) from exc

    if response.status_code != 200:
        raise ArbiterUnavailableError(
            f"Unexpected Arbiter response: "
            f"HTTP {response.status_code}"
        )

    entries = body.get("entries")

    if not isinstance(entries, list):
        raise ArbiterUnavailableError(
            "Arbiter returned invalid WAL entries."
        )

    return entries