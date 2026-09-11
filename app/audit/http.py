from fastapi import Request
from sqlalchemy.orm import Session

from app.audit.service import record_event


def record_early_rejection(request: Request, status_code: int) -> None:
    """补记材料与聊天接口在身份/来源/参数检查阶段的拒绝，不重复记录。"""
    if getattr(request.state, "gateway_started", False):
        return
    route_path = getattr(request.scope.get("route"), "path", None)
    tool_name = {
        ("GET", "/applications"): "list_applications",
        ("GET", "/applications/{application_id}"): "read_application",
        ("POST", "/chat"): "chat_request",
    }.get((request.method, route_path))
    if tool_name is None or status_code not in (401, 403, 422):
        return
    raw_id = request.path_params.get("application_id")
    application_id = None
    if isinstance(raw_id, str) and len(raw_id) <= 19 and raw_id.isascii() and raw_id.isdecimal():
        application_id = int(raw_id)
    user_id, role = getattr(request.state, "audit_actor", (None, None))
    with Session(request.app.state.engine) as db:
        record_event(
            db, request_id=request.state.request_id, user_id=user_id, role=role,
            tool_name=tool_name, application_id=application_id,
            decision="DENY",
            reason_code={401: "NOT_AUTHENTICATED", 403: "CSRF_REJECTED", 422: "INVALID_ARGUMENTS"}[status_code],
            execution_status="NOT_EXECUTED",
        )
