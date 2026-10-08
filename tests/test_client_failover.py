import httpx

import client.stress_client as stress_client


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        body: dict,
    ):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


def test_client_moves_to_second_server(
    monkeypatch,
):
    seen = []

    def fake_post(
        url,
        json,
        timeout,
    ):
        seen.append(
            {
                "url": url,
                "payload": dict(json),
            }
        )

        if "server-a" in url:
            request = httpx.Request(
                "POST",
                url,
            )

            raise httpx.ConnectError(
                "Server A is down",
                request=request,
            )

        return FakeResponse(
            200,
            {
                "status": "success",
                "request_id": (
                    json["request_id"]
                ),
                "account": "A1001",
                "balance": 900,
            },
        )

    monkeypatch.setattr(
        stress_client.httpx,
        "post",
        fake_post,
    )

    payload = {
        "request_id": "same-id-001",
        "action": "withdraw",
        "account": "A1001",
        "amount": 100,
    }

    result = (
        stress_client
        .send_transaction_with_failover(
            base_urls=[
                "http://server-a:8000",
                "http://server-b:8000",
            ],
            payload=payload,
            failover_timeout=1,
            retry_delay=0,
            request_timeout=1,
        )
    )

    assert (
        result["body"]["status"]
        == "success"
    )

    assert (
        result["server"]
        == "http://server-b:8000"
    )

    assert len(seen) == 2

    assert (
        seen[0]["payload"]["request_id"]
        == "same-id-001"
    )

    assert (
        seen[1]["payload"]["request_id"]
        == "same-id-001"
    )


def test_not_primary_retries_other_server(
    monkeypatch,
):
    seen = []

    def fake_post(
        url,
        json,
        timeout,
    ):
        seen.append(url)

        if "server-a" in url:
            return FakeResponse(
                503,
                {
                    "status": "error",
                    "code": "NOT_PRIMARY",
                },
            )

        return FakeResponse(
            200,
            {
                "status": "success",
                "request_id": (
                    json["request_id"]
                ),
                "account": "A1001",
                "balance": 900,
            },
        )

    monkeypatch.setattr(
        stress_client.httpx,
        "post",
        fake_post,
    )

    result = (
        stress_client
        .send_transaction_with_failover(
            base_urls=[
                "http://server-a:8000",
                "http://server-b:8000",
            ],
            payload={
                "request_id": "retry-001",
                "action": "withdraw",
                "account": "A1001",
                "amount": 100,
            },
            failover_timeout=1,
            retry_delay=0,
            request_timeout=1,
        )
    )

    assert (
        result["body"]["status"]
        == "success"
    )

    assert seen == [
        (
            "http://server-a:8000"
            "/api/transaction"
        ),
        (
            "http://server-b:8000"
            "/api/transaction"
        ),
    ]


def test_insufficient_funds_is_not_retried(
    monkeypatch,
):
    seen = []

    def fake_post(
        url,
        json,
        timeout,
    ):
        seen.append(url)

        return FakeResponse(
            409,
            {
                "status": "error",
                "code": "INSUFFICIENT_FUNDS",
            },
        )

    monkeypatch.setattr(
        stress_client.httpx,
        "post",
        fake_post,
    )

    result = (
        stress_client
        .send_transaction_with_failover(
            base_urls=[
                "http://server-a:8000",
                "http://server-b:8000",
            ],
            payload={
                "request_id": "funds-001",
                "action": "withdraw",
                "account": "A1001",
                "amount": 5000,
            },
            failover_timeout=1,
            retry_delay=0,
            request_timeout=1,
        )
    )

    assert (
        result["body"]["code"]
        == "INSUFFICIENT_FUNDS"
    )

    # Business errors must not be retried
    # on another node.
    assert len(seen) == 1


def test_stale_epoch_is_retryable(
    monkeypatch,
):
    seen = []

    def fake_post(
        url,
        json,
        timeout,
    ):
        seen.append(url)

        if "server-a" in url:
            return FakeResponse(
                503,
                {
                    "status": "error",
                    "code": "STALE_EPOCH",
                },
            )

        return FakeResponse(
            200,
            {
                "status": "success",
                "request_id": (
                    json["request_id"]
                ),
                "account": "A1001",
                "balance": 950,
            },
        )

    monkeypatch.setattr(
        stress_client.httpx,
        "post",
        fake_post,
    )

    result = (
        stress_client
        .send_transaction_with_failover(
            base_urls=[
                "http://server-a:8000",
                "http://server-b:8000",
            ],
            payload={
                "request_id": "epoch-001",
                "action": "withdraw",
                "account": "A1001",
                "amount": 50,
            },
            failover_timeout=1,
            retry_delay=0,
            request_timeout=1,
        )
    )

    assert (
        result["body"]["status"]
        == "success"
    )

    assert len(seen) == 2