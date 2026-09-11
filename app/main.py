from contextlib import asynccontextmanager
import os
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from app.audit.http import record_early_rejection
from app.audit.service import AuditUnavailable
from app.crypto.field_encryption import ContentAccessError, FieldEncryption
from app.crypto.keys import load_configured_key
from app.gateway.service import GatewayExecutionError
from app.database.models import Base
from app.database.session import DATABASE_PATH, create_db_engine
from app.routes.auth import router as auth_router
from app.routes.applications import router as applications_router
from app.routes.audit import router as audit_router
from app.routes.chat import router as chat_router
from app.agent.deepseek import DeepSeekClient
from app.agent.rate_limit import UserModelRateLimiter
from app.auth.rate_limit import LoginRateLimiter


def create_app(
    database_path: Path = DATABASE_PATH, *, secure_cookie: bool = False,
    encryption_key: bytes | None = None, load_encryption_config: bool = False,
    agent_mode: str = "mock", deepseek_api_key: str | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        engine = create_db_engine(database_path)
        application.state.engine = engine
        try:
            if agent_mode not in ("mock", "deepseek"):
                raise ValueError("Unsupported agent mode")
            application.state.agent_mode = agent_mode
            application.state.model_rate_limiter = UserModelRateLimiter()
            application.state.login_rate_limiter = LoginRateLimiter()
            application.state.deepseek_client = DeepSeekClient(deepseek_api_key or "") if agent_mode == "deepseek" else None
            # 只创建缺少的表，不重建已有表，也不自动创建演示账户。
            Base.metadata.create_all(engine)
            # 测试显式注入独立密钥；正常服务加载环境变量或本地配置文件。
            key = load_configured_key() if load_encryption_config else encryption_key
            application.state.field_encryption = FieldEncryption(key) if key is not None else None
            yield
        finally:
            engine.dispose()

    application = FastAPI(
        title="AI Secure Gateway",
        description="AI 数据访问安全网关：可选 DeepSeek 单次工具提议、独立授权、加密正文与审计；默认模拟模式。",
        version="0.8.0",
        lifespan=lifespan,
    )
    application.state.secure_cookie = secure_cookie

    @application.exception_handler(ContentAccessError)
    async def content_unavailable(_request: Request, _error: ContentAccessError):
        return JSONResponse(status_code=503, content={"detail": "Application content unavailable"})

    @application.exception_handler(AuditUnavailable)
    async def audit_unavailable(_request: Request, _error: AuditUnavailable):
        return JSONResponse(status_code=503, content={"detail": "Audit logging unavailable"})

    @application.exception_handler(GatewayExecutionError)
    async def gateway_failed(_request: Request, _error: GatewayExecutionError):
        return JSONResponse(status_code=503, content={"detail": "Gateway execution failed"})

    @application.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, _error: RequestValidationError):
        # 默认校验错误可能回显输入；统一错误避免密码出现在返回值中。
        return JSONResponse(status_code=422, content={"detail": "Invalid request parameters"})

    @application.middleware("http")
    async def prevent_private_caching(request: Request, call_next):
        # 不信任客户端自带的请求编号，每次由服务器生成新的关联标识。
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        try:
            await run_in_threadpool(record_early_rejection, request, response.status_code)
        except AuditUnavailable:
            response = JSONResponse(status_code=503, content={"detail": "Audit logging unavailable"})
        response.headers["X-Request-ID"] = request.state.request_id
        if request.url.path == "/" or request.url.path.startswith(("/auth/", "/applications", "/audit/", "/chat", "/ui/", "/static/")):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        if request.url.path == "/" or request.url.path.startswith("/static/"):
            response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["X-Frame-Options"] = "DENY"
        return response

    web_path = Path(__file__).resolve().parent / "web"
    application.mount("/static", StaticFiles(directory=web_path), name="static")

    @application.get("/", include_in_schema=False)
    def demo_page():
        return FileResponse(web_path / "index.html", media_type="text/html")

    @application.get("/ui/config", include_in_schema=False)
    def ui_config():
        # 仅公开展示模式，不暴露密钥、环境变量或其他用户的调用计数。
        return {"mode": application.state.agent_mode, "version": application.version}

    @application.get("/health", summary="检查服务是否运行")
    def health() -> dict[str, str]:
        """只确认服务能够响应请求，不代表完整安全功能已经实现。"""
        return {"status": "ok"}

    application.include_router(auth_router)
    application.include_router(applications_router)
    application.include_router(audit_router)
    application.include_router(chat_router)
    return application


# 本机 HTTP 演示默认关闭 Secure；使用 HTTPS 时应设置为 1。
app = create_app(secure_cookie=os.environ.get("AI_SECURE_COOKIE_SECURE") == "1", load_encryption_config=True)
