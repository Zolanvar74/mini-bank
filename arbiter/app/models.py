from typing import Literal, Any

from pydantic import BaseModel, Field


class AcquireLeaseRequest(BaseModel):
    node_id: Literal["A", "B"]


class RenewLeaseRequest(BaseModel):
    node_id: Literal["A", "B"]
    epoch: int = Field(gt=0)
    
class WalCommitRequest(BaseModel):
    node_id: Literal["A", "B"]
    epoch: int = Field(gt=0)

    request_id: str
    action: Literal["deposit", "withdraw"]
    account_id: str
    amount: int = Field(gt=0)

    status: str
    balance_after: int | None = None
    response_json: dict[str, Any]