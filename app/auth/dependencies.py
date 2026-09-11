from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth.service import COOKIE_NAME, user_from_session
from app.database.models import User


def get_db(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as db:
        yield db


def get_current_user(request: Request, db: Annotated[Session, Depends(get_db)]) -> User:
    user = user_from_session(db, request.cookies.get(COOKIE_NAME))
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    # 仅保存服务器已认证的身份，供参数校验失败时补记审计。
    request.state.audit_actor = (user.id, user.role)
    return user


def require_same_origin(
    request: Request,
    x_csrf_protection: Annotated[str | None, Header()] = None,
) -> None:
    # 自定义请求头不能由普通跨站 HTML 表单设置；本应用不开放跨域访问。
    # 这不是秘密令牌，而是要求浏览器执行同源限制的标记。
    if x_csrf_protection != "1":
        raise HTTPException(status_code=403, detail="CSRF check failed")
    origin = request.headers.get("origin")
    expected_origin = f"{request.url.scheme}://{request.url.netloc}"
    if origin is not None and origin != expected_origin:
        raise HTTPException(status_code=403, detail="CSRF check failed")
