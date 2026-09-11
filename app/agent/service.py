from collections.abc import Callable
from typing import Literal

from app.agent.provider import AgentProvider
from app.agent.schemas import ChatResponse, ToolCall
from app.gateway.schemas import ApplicationDetail, GatewayResult


def run_agent(
    *, message: str, provider: AgentProvider,
    execute: Callable[[ToolCall], GatewayResult], request_id: str,
    mode: Literal["mock", "deepseek"] = "mock",
) -> ChatResponse:
    """每次最多提出并执行一个调用；无跨用户历史，不自行读取数据。"""
    proposal = provider.propose(message)
    usage = getattr(provider, "usage", None)
    if proposal is None:
        return ChatResponse(
            status="needs_clarification",
            answer="本次没有提出工具调用。请明确要列出材料，还是读取某个材料编号；每次只读取一份。",
            request_id=request_id, mode=mode, usage=usage,
        )

    result = execute(proposal)
    if result.decision == "DENY":
        answer = "网关拒绝了这次调用，没有返回材料正文。请检查目标编号及当前账户权限。"
    elif isinstance(result.data, ApplicationDetail):
        answer = result.data.personal_statement
    elif isinstance(result.data, list):
        answer = "\n".join(f"材料 {item.id}：{item.title}" for item in result.data) or "目前没有可访问的材料。"
    else:
        answer = "调用已完成。"
    return ChatResponse(
        status="completed" if result.decision == "ALLOW" else "denied",
        answer=answer, tool_call=proposal, gateway_result=result, request_id=request_id, mode=mode, usage=usage,
    )
