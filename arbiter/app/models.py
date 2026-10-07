from typing import Literal

from pydantic import BaseModel, Field


class AcquireLeaseRequest(BaseModel):
    node_id: Literal["A", "B"]


class RenewLeaseRequest(BaseModel):
    node_id: Literal["A", "B"]
    epoch: int = Field(gt=0)