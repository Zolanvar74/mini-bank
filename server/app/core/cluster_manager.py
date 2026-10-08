import asyncio
import time

import httpx

from server.app.core.config import settings


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
                "lease_expires_at": self.lease_expires_at,
                "lease_valid": local_lease_valid,
                "last_error": self.last_error,
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
            self.lease_expires_at = lease_expires_at
            self.last_error = last_error

    async def _acquire(
        self,
        client: httpx.AsyncClient,
    ):
        try:
            response = await client.post(
                f"{settings.arbiter_url}/cluster/acquire",
                json={
                    "node_id": settings.node_id,
                },
            )

        except httpx.RequestError:
            await self._set_state(
                role="FOLLOWER",
                epoch=self.epoch,
                lease_expires_at=self.lease_expires_at,
                last_error="ARBITER_UNREACHABLE",
            )
            return

        body = response.json()

        if response.status_code == 200:
            await self._set_state(
                role="PRIMARY",
                epoch=body["epoch"],
                lease_expires_at=body["lease_expires_at"],
                last_error=None,
            )
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
                f"ARBITER_HTTP_{response.status_code}"
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
                f"{settings.arbiter_url}/cluster/renew",
                json={
                    "node_id": settings.node_id,
                    "epoch": self.epoch,
                },
            )

        except httpx.RequestError:
            if (
                self.lease_expires_at is not None
                and time.time()
                < self.lease_expires_at
            ):
                async with self._lock:
                    self.last_error = (
                        "ARBITER_UNREACHABLE"
                    )
                return

            await self._set_state(
                role="FENCED",
                epoch=self.epoch,
                lease_expires_at=self.lease_expires_at,
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
                f"ARBITER_HTTP_{response.status_code}",
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
                    if (
                        self.role == "PRIMARY"
                        and self.lease_expires_at
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

                    if self.role == "PRIMARY":
                        await self._renew(client)

                    elif (
                        self.role == "FOLLOWER"
                        and settings.auto_acquire_enabled
                    ):
                        await self._acquire(client)

                    await asyncio.sleep(
                        settings.heartbeat_interval_ms
                        / 1000.0
                    )

                except asyncio.CancelledError:
                    raise

                except Exception as exc:
                    async with self._lock:
                        self.last_error = (
                            "HEARTBEAT_ERROR: "
                            f"{type(exc).__name__}"
                        )

                    await asyncio.sleep(
                        settings.heartbeat_interval_ms
                        / 1000.0
                    )