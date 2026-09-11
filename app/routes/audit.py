from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.schemas import AuditEntry
from app.auth.dependencies import get_current_user, get_db
from app.database.models import AuditLog, User


router = APIRouter(prefix="/audit", tags=["审计日志"])


def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@router.get("/logs", response_model=list[AuditEntry], summary="仅管理员可查看最近的材料访问日志")
def list_audit_logs(
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100, description="最多返回几条记录，默认 20")] = 20,
    offset: Annotated[int, Query(ge=0, le=2**63 - 1, description="跳过最新的几条记录，默认 0")] = 0,
):
    return list(db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit).offset(offset)))
