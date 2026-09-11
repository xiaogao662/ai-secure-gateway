from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.gateway.schemas import GatewayResult


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    message: str = Field(min_length=1, max_length=1000, examples=["列出我能访问的材料"])

    @field_validator("message")
    @classmethod
    def nonblank_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message must not be blank")
        return value.strip()


class ToolCall(BaseModel):
    """不可信的调用提议；是否属于允许的工具、参数仍由网关判断。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    tool_name: str = Field(min_length=1, max_length=64)
    arguments: dict


class TokenUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    prompt_tokens: int | None = Field(default=None, ge=0, le=10**9)
    completion_tokens: int | None = Field(default=None, ge=0, le=10**9)
    total_tokens: int | None = Field(default=None, ge=0, le=10**9)


class ChatResponse(BaseModel):
    mode: Literal["mock", "deepseek"] = "mock"
    status: Literal["completed", "denied", "needs_clarification"]
    answer: str
    tool_call: ToolCall | None = None
    gateway_result: GatewayResult | None = None
    request_id: str
    usage: TokenUsage | None = None
