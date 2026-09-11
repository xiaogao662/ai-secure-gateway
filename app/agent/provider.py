import re
from typing import Protocol
from fastapi import Request

from app.agent.schemas import ToolCall
from app.agent.deepseek import DeepSeekProvider


class AgentProvider(Protocol):
    def propose(self, message: str) -> ToolCall | None: ...


class MockAgentProvider:
    """固定规则模拟工具选择，不是真实大模型，也不检查用户权限。"""

    def propose(self, message: str) -> ToolCall | None:
        normalized = message.strip().rstrip("。！？!?")
        if normalized in {"列出我能访问的材料", "列出我的材料", "查看我的材料"}:
            return ToolCall(tool_name="list_applications", arguments={})

        # 允许前缀中含有越权指令，以演示提议不等于授权。多编号不猜测。
        numbers = re.findall(r"[0-9]+", normalized)
        match = re.search(r"(?:读取|查看)\s*材料\s*(?:编号\s*)?([0-9]+)\s*$", normalized)
        if match is None or len(numbers) != 1:
            return None
        # 超大编号仍交给网关作参数拒绝，但不转换任意长度的整数字符串。
        number = match.group(1)
        target = int(number) if len(number) <= 19 else 2**63
        return ToolCall(tool_name="read_application", arguments={"application_id": target})


def get_agent_provider(request: Request) -> AgentProvider:
    if request.app.state.agent_mode == "deepseek":
        return DeepSeekProvider(request.app.state.deepseek_client)
    return MockAgentProvider()
