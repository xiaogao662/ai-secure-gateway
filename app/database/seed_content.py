"""初始化加密的虚构正文；无覆盖、无密钥输出、无真实申请材料。"""

from pathlib import Path

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.crypto.field_encryption import FieldEncryption
from app.crypto.keys import KEY_FILE, KeyConfigurationError, create_local_key, load_configured_key
from app.database.models import Application, ApplicationContent, Base, User
from app.database.session import create_db_engine


# 公开虚构示例，源代码中出现这些文字是为了可重复演示，不是真实用户数据。
DEMO_STATEMENTS = {
    "alice": "虚构演示：我是 Alice，希望申请计算机安全方向研究生，研究兴趣是 AI Agent 的访问控制。",
    "bob": "虚构演示：我是 Bob，希望申请软件工程方向研究生，计划研究可靠的后端系统。",
    "carol": "虚构演示：我是 Carol，希望申请密码学方向研究生，研究兴趣是认证加密与密钥管理。",
}


def _demo_applications(db: Session) -> dict[str, Application]:
    rows = db.execute(
        select(User.username, Application).join(Application, Application.owner_id == User.id)
        .where(User.username.in_(DEMO_STATEMENTS), User.role == "student"),
    )
    applications = {name: application for name, application in rows}
    if set(applications) != set(DEMO_STATEMENTS):
        raise ValueError("Initialize the three student accounts and application metadata first")
    return applications


def seed_content(engine: Engine, cipher: FieldEncryption) -> int:
    Base.metadata.create_all(engine)
    created = 0
    with Session(engine) as db, db.begin():
        applications = _demo_applications(db)
        # 在添加内容前校验全部已有密文，防止用错误的新密钥混写数据。
        for content, application in db.execute(
            select(ApplicationContent, Application).join(Application, ApplicationContent.application_id == Application.id),
        ):
            cipher.decrypt(content.nonce, content.ciphertext, application_id=application.id, owner_id=application.owner_id)
        for name, application in applications.items():
            if db.get(ApplicationContent, application.id) is not None:
                continue
            nonce, ciphertext = cipher.encrypt(
                DEMO_STATEMENTS[name], application_id=application.id, owner_id=application.owner_id,
            )
            db.add(ApplicationContent(application_id=application.id, nonce=nonce, ciphertext=ciphertext))
            created += 1
    return created


def initialize_demo_content(engine: Engine, key_file: Path = KEY_FILE) -> int:
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        _demo_applications(db)
        has_content = db.scalar(select(ApplicationContent.application_id).limit(1)) is not None
    key = load_configured_key(key_file)
    if key is None:
        if has_content:
            raise KeyConfigurationError("Encrypted data exists but its key is missing; restore the original key")
        key = create_local_key(key_file)
    return seed_content(engine, FieldEncryption(key))


def main() -> None:
    engine = create_db_engine()
    try:
        count = initialize_demo_content(engine)
        print(f"Created {count} encrypted demo content record(s); existing ciphertext was preserved.")
        print("Key configured separately from the database; key value is never printed.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
