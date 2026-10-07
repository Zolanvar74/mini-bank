from typing import Literal

from pydantic import BaseModel


class TransactionRequest(BaseModel):
    action: Literal["balance", "deposit", "withdraw"]
    account: str
    amount: int | None = None


class SuccessResponse(BaseModel):
    status: str = "success"
    account: str
    balance: int