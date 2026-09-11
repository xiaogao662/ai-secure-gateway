import hashlib
import re
import secrets
import time

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password, verify_password
from app.database.models import LoginSession, User


COOKIE_NAME = "ai_secure_session"
SESSION_TTL_SECONDS = 60 * 60
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}")
# 用户不存在时也做一次密码校验，减少通过响应耗时猜用户名的差异。
_DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))


def token_digest(token: str | None) -> str | None:
    if token is None or not _TOKEN_PATTERN.fullmatch(token):
        return None
    # 随机令牌具有 256 位熵，使用快速摘要即可；用户密码仍使用 Argon2id。
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def authenticate(db: Session, username: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.username == username))
    saved_hash = user.password_hash if user else _DUMMY_PASSWORD_HASH
    valid = verify_password(password, saved_hash)
    return user if valid and user is not None else None


def create_login_session(db: Session, user: User, old_token: str | None) -> str:
    now = int(time.time())
    db.execute(delete(LoginSession).where(LoginSession.expires_at <= now))
    old_digest = token_digest(old_token)
    if old_digest is not None:
        db.execute(delete(LoginSession).where(LoginSession.token_hash == old_digest))
    token = secrets.token_urlsafe(32)
    db.add(
        LoginSession(
            token_hash=token_digest(token),
            user_id=user.id,
            expires_at=now + SESSION_TTL_SECONDS,
        )
    )
    # 先成功提交服务端会话，再由接口向浏览器发送 Cookie。
    db.commit()
    return token


def user_from_session(db: Session, token: str | None) -> User | None:
    digest = token_digest(token)
    if digest is None:
        return None
    login_session = db.get(LoginSession, digest)
    if login_session is None or login_session.expires_at <= int(time.time()):
        return None
    # 角色来自用户表，不能从 Cookie、请求参数或 AI 输出中获取。
    return db.get(User, login_session.user_id)


def revoke_login_session(db: Session, token: str | None) -> None:
    digest = token_digest(token)
    if digest is not None:
        db.execute(delete(LoginSession).where(LoginSession.token_hash == digest))
        db.commit()
