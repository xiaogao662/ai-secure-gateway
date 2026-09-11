from sqlalchemy import CheckConstraint, ForeignKey, LargeBinary, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('student', 'advisor', 'admin')",
            name="ck_users_role",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    role: Mapped[str] = mapped_column(String(20))
    password_hash: Mapped[str] = mapped_column(String(255))


class LoginSession(Base):
    __tablename__ = "login_sessions"

    # 浏览器持有随机原始标识，数据库只保存其 SHA-256 摘要。
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    expires_at: Mapped[int] = mapped_column(index=True)


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    # 每个学生一份材料，敏感正文分开保存在 ApplicationContent 的密文中。
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    title: Mapped[str] = mapped_column(String(200))


class ApplicationContent(Base):
    __tablename__ = "application_contents"
    __table_args__ = (
        CheckConstraint("length(nonce) = 12", name="ck_content_nonce_length"),
        CheckConstraint("length(ciphertext) >= 16", name="ck_content_ciphertext_length"),
    )

    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), primary_key=True,
    )
    nonce: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    # AESGCM 返回的密文已包含 16 字节认证标签，不另存明文正文。
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)


class AdvisorAssignment(Base):
    __tablename__ = "advisor_assignments"
    __table_args__ = (
        CheckConstraint("advisor_id != student_id", name="ck_assignment_different_users"),
    )

    # 两个编号共同构成唯一键，同一分配关系不能重复。
    advisor_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True,
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True,
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        CheckConstraint("decision IN ('ALLOW', 'DENY')", name="ck_audit_decision"),
        CheckConstraint("execution_status IN ('SUCCESS', 'NOT_EXECUTED', 'ERROR')", name="ck_audit_execution_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[str] = mapped_column(String(32))
    request_id: Mapped[str] = mapped_column(String(36), index=True)
    # 保留事件发生时的身份快照，不因删除用户/材料而级联删除历史记录。
    user_id: Mapped[int | None]
    role: Mapped[str | None] = mapped_column(String(20))
    tool_name: Mapped[str] = mapped_column(String(32))
    application_id: Mapped[int | None]
    decision: Mapped[str] = mapped_column(String(5))
    reason_code: Mapped[str] = mapped_column(String(64))
    execution_status: Mapped[str] = mapped_column(String(16))
