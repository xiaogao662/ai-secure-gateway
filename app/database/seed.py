"""通过 python -m app.database.seed 显式初始化本地虚构账户。"""

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password
from app.database.models import Base, User
from app.database.session import DATABASE_PATH, create_db_engine


# 公开的本地演示凭证，不得用于真实账户或公网部署。
DEMO_USERS = (
    ("alice", "student", "Alice-demo-2026!"),
    ("bob", "student", "Bob-demo-2026!"),
    ("carol", "student", "Carol-demo-2026!"),
    ("lee", "advisor", "Lee-demo-2026!"),
    ("admin", "admin", "Admin-demo-2026!"),
)


def seed_users(engine: Engine) -> list[str]:
    """只添加缺少的演示账户，不修改已有账户；返回新建的用户名。"""
    Base.metadata.create_all(engine)
    created = []
    # 事务保证账户写入要么全部成功，要么全部撤销。
    with Session(engine) as session, session.begin():
        existing = set(session.scalars(select(User.username)))
        for username, role, password in DEMO_USERS:
            if username in existing:
                continue
            session.add(
                User(
                    username=username,
                    role=role,
                    password_hash=hash_password(password),
                )
            )
            created.append(username)
    return created


def main() -> None:
    engine = create_db_engine()
    try:
        created = seed_users(engine)
        print(f"Database: {DATABASE_PATH}")
        print(f"Created {len(created)} demo user(s); existing users were preserved.")
        with Session(engine) as session:
            for user in session.scalars(select(User).order_by(User.id)):
                print(f"{user.id}: {user.username} ({user.role})")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
