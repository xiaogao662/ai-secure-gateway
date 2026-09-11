from typing import Literal

from pydantic import BaseModel, ConfigDict


class AuditEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: str
    request_id: str
    user_id: int | None
    role: str | None
    tool_name: str
    application_id: int | None
    decision: Literal["ALLOW", "DENY"]
    reason_code: str
    execution_status: Literal["SUCCESS", "NOT_EXECUTED", "ERROR"]
