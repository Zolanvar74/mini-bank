from typing import Literal

from pydantic import BaseModel


class AcquireLeaseRequest(BaseModel):
    node_id: Literal["A", "B"]