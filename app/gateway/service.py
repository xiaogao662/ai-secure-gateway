from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session
from uuid import uuid4

from app.audit.service import record_event
from app.crypto.field_encryption import ContentAccessError, FieldEncryption
from app.database.models import Application, ApplicationContent, User
from app.gateway.policies import visible_application_filter
from app.gateway.schemas import ApplicationDetail, ApplicationSummary, GatewayResult, NoArguments, ReadArguments


class GatewayExecutionError(Exception):
    """网关内部失败，禁止返回部分数据或异常细节。"""


def execute_tool(
    db: Session,
    *,
    current_user_id: int,
    tool_name: str,
    arguments: dict,
    request_id: str | None = None,
    cipher: FieldEncryption | None = None,
) -> GatewayResult:
    """受控访问入口。current_user_id 必须由后端登录身份提供，不是工具参数。

    列表只返回编号和标题；单份读取在授权后解密，日志提交成功后才返回结果。
    """
    event_id = request_id or str(uuid4())
    actor_id, actor_role = None, None
    target_id = arguments.get("application_id") if isinstance(arguments, dict) else None
    try:
        user = db.get(User, current_user_id, populate_existing=True)
        if user is not None:
            actor_id, actor_role = user.id, user.role
        result = _execute_application_tool(db, user=user, tool_name=tool_name, arguments=arguments, cipher=cipher)
    except ContentAccessError as error:
        db.rollback()
        record_event(
            db, request_id=event_id, user_id=actor_id, role=actor_role,
            tool_name=tool_name, application_id=target_id, decision="ALLOW",
            reason_code=error.reason_code, execution_status="ERROR",
        )
        raise
    except Exception as error:
        db.rollback()
        record_event(
            db, request_id=event_id, user_id=actor_id, role=actor_role,
            tool_name=tool_name, application_id=target_id, decision="DENY",
            reason_code="GATEWAY_ERROR", execution_status="ERROR",
        )
        raise GatewayExecutionError("Gateway execution failed") from error
    record_event(
        db, request_id=event_id, user_id=actor_id, role=actor_role,
        tool_name=tool_name, application_id=target_id,
        decision=result.decision, reason_code=result.reason_code,
        execution_status="SUCCESS" if result.decision == "ALLOW" else "NOT_EXECUTED",
    )
    return result


def _execute_application_tool(
    db: Session, *, user: User | None, tool_name: str, arguments: dict, cipher: FieldEncryption | None,
) -> GatewayResult:
    if user is None:
        return GatewayResult(decision="DENY", reason_code="NOT_AUTHENTICATED")

    # 工具名称必须明确列在允许清单里，不动态执行输入指定的函数。
    if tool_name not in ("list_applications", "read_application"):
        return GatewayResult(decision="DENY", reason_code="TOOL_NOT_ALLOWED")
    try:
        parsed = (
            NoArguments.model_validate(arguments)
            if tool_name == "list_applications"
            else ReadArguments.model_validate(arguments)
        )
    except ValidationError:
        return GatewayResult(decision="DENY", reason_code="INVALID_ARGUMENTS")
    if user.role not in ("student", "advisor", "admin"):
        return GatewayResult(decision="DENY", reason_code="ROLE_NOT_ALLOWED")

    # 权限条件直接进入查询；不先加载所有材料再在返回时过滤。
    # 只选编号和标题，以后新增密文字段也不会在此处被自动读出。
    permitted = select(Application.id, Application.title).where(visible_application_filter(user))
    if tool_name == "list_applications":
        rows = db.execute(permitted.order_by(Application.id))
        summaries = [ApplicationSummary(id=row.id, title=row.title) for row in rows]
        return GatewayResult(decision="ALLOW", reason_code="AUTHORIZED", data=summaries)

    row = db.execute(permitted.where(Application.id == parsed.application_id)).one_or_none()
    if row is None:
        # 不区分“他人材料”与“不存在”，避免通过错误信息枚举材料。
        return GatewayResult(decision="DENY", reason_code="APPLICATION_NOT_FOUND_OR_FORBIDDEN")

    # 到这里才允许接触密文或调用解密。缺少密钥不能变成明文降级。
    if cipher is None:
        raise ContentAccessError("ENCRYPTION_NOT_CONFIGURED")
    # 再次在密文查询中带上相同权限条件，避免脱离授权范围的裸读。
    content_row = db.execute(
        select(ApplicationContent.nonce, ApplicationContent.ciphertext, Application.owner_id)
        .join(Application, ApplicationContent.application_id == Application.id)
        .where(Application.id == row.id, visible_application_filter(user)),
    ).one_or_none()
    if content_row is None:
        raise ContentAccessError("CONTENT_NOT_INITIALIZED")
    plaintext = cipher.decrypt(
        content_row.nonce, content_row.ciphertext, application_id=row.id, owner_id=content_row.owner_id,
    )
    return GatewayResult(
        decision="ALLOW", reason_code="AUTHORIZED",
        data=ApplicationDetail(id=row.id, title=row.title, personal_statement=plaintext),
    )
