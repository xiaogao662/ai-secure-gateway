from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, get_db, require_same_origin
from app.auth.schemas import LoginRequest, UserResponse
from app.auth.service import (
    COOKIE_NAME,
    SESSION_TTL_SECONDS,
    authenticate,
    create_login_session,
    revoke_login_session,
)
from app.database.models import User


router = APIRouter(prefix="/auth", tags=["身份认证"])


@router.post(
    "/login",
    response_model=UserResponse,
    dependencies=[Depends(require_same_origin)],
    summary="登录并建立服务器端会话",
    responses={429: {"description": "登录请求频率超限，未校验密码"}},
)
def login(
    credentials: LoginRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> User | JSONResponse:
    retry_after = request.app.state.login_rate_limiter.reserve(credentials.username)
    if retry_after:
        return JSONResponse(
            status_code=429, headers={"Retry-After": str(retry_after)},
            content={"detail": "Too many login attempts", "reason_code": "LOGIN_RATE_LIMIT",
                     "retry_after_seconds": retry_after},
        )
    user = authenticate(db, credentials.username, credentials.password.get_secret_value())
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_login_session(db, user, request.cookies.get(COOKIE_NAME))
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=request.app.state.secure_cookie,
        samesite="strict",
        path="/",
    )
    return user


@router.get("/me", response_model=UserResponse, summary="查看当前登录用户")
def me(user: Annotated[User, Depends(get_current_user)]) -> User:
    return user


@router.post(
    "/logout",
    dependencies=[Depends(require_same_origin)],
    summary="退出并撤销当前会话",
)
def logout(
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    revoke_login_session(db, request.cookies.get(COOKIE_NAME))
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
        httponly=True,
        secure=request.app.state.secure_cookie,
        samesite="strict",
    )
    return {"status": "logged_out"}
