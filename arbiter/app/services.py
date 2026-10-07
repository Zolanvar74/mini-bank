import time

from arbiter.app.config import settings
from arbiter.app.database import get_connection


class LeaseHeldError(Exception):
    def __init__(
        self,
        leader_id: str,
        epoch: int,
        lease_expires_at: float,
    ):
        self.leader_id = leader_id
        self.epoch = epoch
        self.lease_expires_at = lease_expires_at

        super().__init__(
            f"Lease is currently held by node {leader_id}"
        )


def acquire_leadership(node_id: str) -> dict:
    connection = get_connection()

    try:
        # Prevent two servers from acquiring leadership concurrently.
        connection.execute("BEGIN IMMEDIATE")

        row = connection.execute(
            """
            SELECT leader_id, epoch, lease_expires_at
            FROM cluster_state
            WHERE id = 1
            """
        ).fetchone()

        now = time.time()

        current_leader = row["leader_id"]
        current_epoch = row["epoch"]
        current_expiry = row["lease_expires_at"]

        lease_is_valid = (
            current_leader is not None
            and current_expiry is not None
            and current_expiry > now
        )

        if lease_is_valid:
            connection.rollback()

            raise LeaseHeldError(
                leader_id=current_leader,
                epoch=current_epoch,
                lease_expires_at=current_expiry,
            )

        new_epoch = current_epoch + 1

        lease_expires_at = (
            now + settings.lease_ttl_ms / 1000.0
        )

        connection.execute(
            """
            UPDATE cluster_state
            SET leader_id = ?,
                epoch = ?,
                lease_expires_at = ?
            WHERE id = 1
            """,
            (
                node_id,
                new_epoch,
                lease_expires_at,
            ),
        )

        connection.commit()

        return {
            "leader_id": node_id,
            "epoch": new_epoch,
            "lease_expires_at": lease_expires_at,
        }

    except LeaseHeldError:
        raise

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()