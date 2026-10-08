import asyncio
import time

import httpx

from server.app.core.config import settings
from server.app.core.wal_client import (
    ArbiterUnavailableError,
)
from server.app.services.replica_service import (
    ReplicaApplyError,
    ReplicaGapError,
    sync_from_arbiter,
)


class ClusterManager:
    def __init__(self):
        self.role = (
            "FOLLOWER"
            if settings.cluster_enabled
            else "DISABLED"
        )

        self.epoch: int | None = None
        self.lease_expires_at: float | None = None
        self.last_error: str | None = None

        self.last_sync_error: str | None = None
        self.last_sync_at: float | None = None
        self.last_sync_result: dict | None = None

        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    async def start(self):
        if not settings.cluster_enabled:
            return

        self._task = asyncio.create_task(
            self._heartbeat_loop()
        )

    async def stop(self):
        if self._task is None:
            return

        self._task.cancel()

        try:
            await self._task
        except asyncio.CancelledError:
            pass

        self._task = None

    async def snapshot(self) -> dict:
        async with self._lock:
            local_lease_valid = (
                self.lease_expires_at is not None
                and self.lease_expires_at > time.time()
            )

            return {
                "node_id": settings.node_id,
                "role": self.role,
                "epoch": self.epoch,
                "lease_expires_at": (
                    self.lease_expires_at
                ),
                "lease_valid": local_lease_valid,
                "last_error": self.last_error,
                "last_sync_error": (
                    self.last_sync_error
                ),
                "last_sync_at": self.last_sync_at,
                "last_sync_result": (
                    self.last_sync_result
                ),
                "auto_acquire_enabled": (
                    settings.auto_acquire_enabled
                ),
            }

    def write_context(self) -> dict:
        lease_valid = (
            self.lease_expires_at is not None
            and self.lease_expires_at > time.time()
        )

        return {
            "role": self.role,
            "epoch": self.epoch,
            "lease_valid": lease_valid,
        }

    def fence_now(self, reason: str) -> None:
        self.role = "FENCED"
        self.last_error = reason

    async def _set_state(
        self,
        *,
        role: str,
        epoch: int | None = None,
        lease_expires_at: float | None = None,
        last_error: str | None = None,
    ):
        async with self._lock:
            self.role = role
            self.epoch = epoch
            self.lease_expires_at = (
                lease_expires_at
            )
            self.last_error = last_error

    async def _sync_replica(self) -> bool:
        try:
            result = await asyncio.to_thread(
                sync_from_arbiter
            )

        except (
            ArbiterUnavailableError,
            ReplicaGapError,
            ReplicaApplyError,
        ) as exc:
            async with self._lock:
                self.last_sync_error = (
                    type(exc).__name__
                )
                self.last_error = (
                    "SYNC_FAILED:"
                    f"{type(exc).__name__}"
                )

            return False

        except Exception as exc:
            async with self._lock:
                self.last_sync_error = (
                    type(exc).__name__
                )
                self.last_error = (
                    "SYNC_FAILED:"
                    f"{type(exc).__name__}"
                )

            return False

        async with self._lock:
            self.last_sync_error = None
            self.last_sync_at = time.time()
            self.last_sync_result = result

        return True

    async def _acquire(
        self,
        client: httpx.AsyncClient,
    ):
        try:
            response = await client.post(
                (
                    f"{settings.arbiter_url}"
                    "/cluster/acquire"
                ),
                json={
                    "node_id": settings.node_id,
                },
            )

        except httpx.RequestError:
            await self._set_state(
                role="FOLLOWER",
                last_error="ARBITER_UNREACHABLE",
            )
            return

        body = response.json()

        if response.status_code == 200:
            epoch = body["epoch"]
            lease_expires_at = body[
                "lease_expires_at"
            ]

            # We own the new epoch, but we are NOT
            # allowed to serve writes yet.
            await self._set_state(
                role="SYNCING",
                epoch=epoch,
                lease_expires_at=lease_expires_at,
                last_error=None,
            )

            # Final catch-up AFTER acquiring the epoch.
            # The old primary cannot append new WAL
            # entries after this leadership change.
            synced = await self._sync_replica()

            if not synced:
                await self._set_state(
                    role="FENCED",
                    epoch=epoch,
                    lease_expires_at=(
                        lease_expires_at
                    ),
                    last_error=(
                        "SYNC_FAILED_AFTER_ACQUIRE"
                    ),
                )
                return

            # Refresh lease after catch-up.
            # _renew() promotes us to PRIMARY only if
            # Arbiter still accepts our epoch.
            await self._renew(client)
            return

        if response.status_code == 409:
            await self._set_state(
                role="FOLLOWER",
                epoch=body.get("epoch"),
                lease_expires_at=body.get(
                    "lease_expires_at"
                ),
                last_error=body.get("code"),
            )
            return

        await self._set_state(
            role="FOLLOWER",
            last_error=(
                f"ARBITER_HTTP_"
                f"{response.status_code}"
            ),
        )

    async def _renew(
        self,
        client: httpx.AsyncClient,
    ):
        if self.epoch is None:
            await self._set_state(
                role="FENCED",
                last_error="MISSING_EPOCH",
            )
            return

        try:
            response = await client.post(
                (
                    f"{settings.arbiter_url}"
                    "/cluster/renew"
                ),
                json={
                    "node_id": settings.node_id,
                    "epoch": self.epoch,
                },
            )

        except httpx.RequestError:
            lease_still_valid = (
                self.lease_expires_at is not None
                and time.time()
                < self.lease_expires_at
            )

            if (
                self.role == "PRIMARY"
                and lease_still_valid
            ):
                async with self._lock:
                    self.last_error = (
                        "ARBITER_UNREACHABLE"
                    )
                return

            await self._set_state(
                role="FENCED",
                epoch=self.epoch,
                lease_expires_at=(
                    self.lease_expires_at
                ),
                last_error="ARBITER_UNREACHABLE",
            )
            return

        body = response.json()

        if response.status_code == 200:
            await self._set_state(
                role="PRIMARY",
                epoch=body["epoch"],
                lease_expires_at=body[
                    "lease_expires_at"
                ],
                last_error=None,
            )
            return

        await self._set_state(
            role="FENCED",
            epoch=body.get(
                "epoch",
                self.epoch,
            ),
            lease_expires_at=body.get(
                "lease_expires_at",
                self.lease_expires_at,
            ),
            last_error=body.get(
                "code",
                (
                    f"ARBITER_HTTP_"
                    f"{response.status_code}"
                ),
            ),
        )

    async def _heartbeat_loop(self):
        timeout = httpx.Timeout(
            settings.cluster_request_timeout_seconds
        )

        async with httpx.AsyncClient(
            timeout=timeout
        ) as client:

            while True:
                try:
                    if self.role == "PRIMARY":
                        if (
                            self.lease_expires_at
                            is not None
                            and time.time()
                            >= self.lease_expires_at
                        ):
                            await self._set_state(
                                role="FENCED",
                                epoch=self.epoch,
                                lease_expires_at=(
                                    self.lease_expires_at
                                ),
                                last_error=(
                                    "LEASE_EXPIRED"
                                ),
                            )

                        else:
                            await self._renew(
                                client
                            )

                    elif self.role in {
                        "FOLLOWER",
                        "FENCED",
                    }:
                        synced = (
                            await self._sync_replica()
                        )

                        if synced:
                            if self.role == "FENCED":
                                await self._set_state(
                                    role="FOLLOWER",
                                    epoch=None,
                                    lease_expires_at=None,
                                    last_error=None,
                                )

                            if (
                                settings
                                .auto_acquire_enabled
                            ):
                                await self._acquire(
                                    client
                                )

                    await asyncio.sleep(
                        settings
                        .heartbeat_interval_ms
                        / 1000.0
                    )

                except asyncio.CancelledError:
                    raise

                except Exception as exc:
                    async with self._lock:
                        self.last_error = (
                            "HEARTBEAT_ERROR:"
                            f"{type(exc).__name__}"
                        )

                    await asyncio.sleep(
                        settings
                        .heartbeat_interval_ms
                        / 1000.0
                    )