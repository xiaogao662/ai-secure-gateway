from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.database.models import AuditLog


class AuditUnavailable(Exception):
    """审计无法持久化时，调用方不得返回材料数据。"""


def safe_application_id(value: object) -> int | None:
    # 不把任意攻击文本、布尔值或超出数据库范围的整数写进目标编号。
    return value if type(value) is int and 0 < value <= 2**63 - 1 else None


def record_event(
    db: Session,
    *,
    request_id: str,
    user_id: int | None,
    role: str | None,
    tool_name: str,
    application_id: object,
    decision: str,
    reason_code: str,
    execution_status: str,
) -> None:
    """提交最小审计记录；仅供后端调用，不接受客户端提供的事件正文。

    当前网关只有读取操作，因此在同一数据库会话提交日志。
    后续如加入写工具，需要同时设计业务变更与审计的事务边界。
    """
    try:
        canonical_id = str(UUID(request_id))
    except (ValueError, TypeError, AttributeError):
        canonical_id = str(uuid4())
    entry = AuditLog(
        timestamp=datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        request_id=canonical_id,
        user_id=user_id,
        role=role if role in ("student", "advisor", "admin") else None,
        # 未知工具名可能包含提示注入文本或秘密，统一使用固定标记。
        tool_name=tool_name if tool_name in ("list_applications", "read_application", "chat_request") else "unknown_tool",
        application_id=safe_application_id(application_id),
        decision=decision,
        reason_code=reason_code,
        execution_status=execution_status,
    )
    try:
        db.add(entry)
        db.commit()
    except Exception as error:
        db.rollback()
        raise AuditUnavailable("Audit logging unavailable") from error
