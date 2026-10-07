from typing import Any

from pydantic import BaseModel


class TransactionRequest(BaseModel):
    request_id: str | None = None
    action: str
    account: str | None = None
    amount: Any = None
    failpoint: str | None = None