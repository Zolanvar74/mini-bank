import time

import pytest

import server.app.core.cluster_manager as cm
from server.app.core.cluster_manager import (
    ClusterManager,
)
from server.app.core.config import settings
from server.app.services.replica_service import (
    ReplicaGapError,
)


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


class SuccessfulArbiterClient:
    def __init__(self):
        self.calls = 0

    async def post(self, url, json):
        self.calls += 1

        return FakeResponse(
            200,
            {
                "status": "success",
                "leader_id": json["node_id"],
                "epoch": 2,
                "lease_expires_at": (
                    time.time() + 10
                ),
            },
        )


@pytest.mark.asyncio
async def test_node_syncs_before_becoming_primary(
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "cluster_enabled",
        True,
    )

    calls = []

    def fake_sync():
        calls.append("sync")

        return {
            "from_seq": 3,
            "fetched": 2,
            "applied": 2,
            "last_seq": 5,
        }

    monkeypatch.setattr(
        cm,
        "sync_from_arbiter",
        fake_sync,
    )

    manager = ClusterManager()
    client = SuccessfulArbiterClient()

    await manager._acquire(client)

    assert calls == ["sync"]
    assert manager.role == "PRIMARY"
    assert manager.epoch == 2

    # acquire + renew
    assert client.calls == 2


@pytest.mark.asyncio
async def test_failed_final_sync_fences_node(
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "cluster_enabled",
        True,
    )

    def broken_sync():
        raise ReplicaGapError("gap")

    monkeypatch.setattr(
        cm,
        "sync_from_arbiter",
        broken_sync,
    )

    manager = ClusterManager()
    client = SuccessfulArbiterClient()

    await manager._acquire(client)

    assert manager.role == "FENCED"
    assert manager.epoch == 2
    assert (
        manager.last_error
        == "SYNC_FAILED_AFTER_ACQUIRE"
    )