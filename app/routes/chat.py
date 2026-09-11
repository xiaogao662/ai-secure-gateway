from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.agent.provider import AgentProvider, get_agent_provider
from app.agent.schemas import ChatRequest, ChatResponse, TokenUsage, ToolCall
from app.agent.service import run_agent
from app.agent.deepseek import ProviderError
from app.audit.service import record_event
from app.auth.dependencies import get_current_user, get_db, require_same_origin
from app.auth.service import COOKIE_NAME, user_from_session
from app.database.models import User
from app.gateway.schemas import GatewayResult, NoArguments
from app.gateway import service as gateway_service


router = APIRouter(tags=["AI 助手"])


@router.post(
    "/chat", response_model=ChatResponse, summary="助手提出调用，由网关独立检查权限",
    responses={403: {"description": "来源检查失败，或网关拒绝工具调用"},
               429: {"description": "当前用户的模型请求频率超限，未调用模型"}},
)
def chat(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    csrf: Annotated[None, Depends(require_same_origin)],
    db: Annotated[Session, Depends(get_db)],
    provider: Annotated[AgentProvider, Depends(get_agent_provider)],
    body: ChatRequest,
    query: Annotated[NoArguments, Query()],
):
    # 固定原请求身份与凭证；不能在模型等待后切换成另一个账户。
    actor_id, actor_role = user.id, user.role
    original_token = request.cookies.get(COOKIE_NAME)

    # 登录、来源及参数验证通过之后，任何模型请求之前预留次数。
    # 绑定用户编号，不绑定可更换的会话或可伪造的请求头。
    if request.app.state.agent_mode == "deepseek":
        retry_after = request.app.state.model_rate_limiter.reserve(actor_id)
        if retry_after:
            record_event(
                db, request_id=request.state.request_id, user_id=actor_id,
                role=actor_role, tool_name="chat_request", application_id=None,
                decision="DENY", reason_code="AI_RATE_LIMIT",
                execution_status="NOT_EXECUTED",
            )
            return JSONResponse(
                status_code=429, headers={"Retry-After": str(retry_after)},
                content={"detail": "Too many model requests", "reason_code": "AI_RATE_LIMIT",
                         "retry_after_seconds": retry_after, "request_id": request.state.request_id},
            )

    def execute(proposal: ToolCall) -> GatewayResult:
        request.state.gateway_started = True
        # 新数据库会话避免复用模型等待前的缓存/事务快照。
        # 此检查约束工具开始前的有效性，不保证执行中撤销的原子性。
        with Session(request.app.state.engine) as execution_db:
            current = user_from_session(execution_db, original_token)
            if current is None or current.id != actor_id:
                record_event(
                    execution_db, request_id=request.state.request_id,
                    user_id=actor_id, role=actor_role, tool_name=proposal.tool_name,
                    application_id=proposal.arguments.get("application_id"),
                    decision="DENY", reason_code="NOT_AUTHENTICATED",
                    execution_status="NOT_EXECUTED",
                )
                return GatewayResult(decision="DENY", reason_code="NOT_AUTHENTICATED")
            return gateway_service.execute_tool(
                execution_db, current_user_id=actor_id, tool_name=proposal.tool_name,
                arguments=proposal.arguments, request_id=request.state.request_id,
                cipher=request.app.state.field_encryption,
            )

    try:
        result = run_agent(
            message=body.message, provider=provider, execute=execute,
            request_id=request.state.request_id, mode=request.app.state.agent_mode,
        )
    except ProviderError as error:
        record_event(
            db, request_id=request.state.request_id, user_id=user.id, role=user.role,
            tool_name="chat_request", application_id=None, decision="DENY",
            reason_code=error.reason_code, execution_status="ERROR",
        )
        content = {"detail": "AI provider unavailable", "reason_code": error.reason_code}
        usage = getattr(provider, "usage", None)
        if isinstance(usage, TokenUsage):
            content["usage"] = usage.model_dump()
        return JSONResponse(status_code=503, content=content)
    if result.gateway_result is not None and result.gateway_result.decision == "DENY":
        status = {"NOT_AUTHENTICATED": 401, "INVALID_ARGUMENTS": 422}.get(result.gateway_result.reason_code, 403)
        return JSONResponse(status_code=status, content=result.model_dump())
    return result
