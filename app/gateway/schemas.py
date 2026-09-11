from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


MAX_APPLICATION_ID = 2**63 - 1


class NoArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ReadArguments(NoArguments):
    application_id: int = Field(gt=0, le=MAX_APPLICATION_ID)


class ApplicationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str


class ApplicationDetail(ApplicationSummary):
    personal_statement: str


class GatewayResult(BaseModel):
    decision: Literal["ALLOW", "DENY"]
    reason_code: Literal[
        "AUTHORIZED", "NOT_AUTHENTICATED", "TOOL_NOT_ALLOWED", "ROLE_NOT_ALLOWED",
        "INVALID_ARGUMENTS", "APPLICATION_NOT_FOUND_OR_FORBIDDEN",
    ]
    data: ApplicationDetail | list[ApplicationSummary] | None = None
