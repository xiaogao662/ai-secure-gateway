"""显式初始化虚构材料和导师关系，不修改已有账户、材料或分配。"""

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.database.models import AdvisorAssignment, Application, Base, User
from app.database.session import DATABASE_PATH, create_db_engine


DEMO_APPLICATIONS = (
    ("alice", "Alice - Demo Application"),
    ("bob", "Bob - Demo Application"),
    ("carol", "Carol - Demo Application"),
)


def seed_applications(engine: Engine) -> dict[str, int]:
    Base.metadata.create_all(engine)
    counts = {"applications": 0, "assignments": 0}
    with Session(engine) as db, db.begin():
        users = {user.username: user for user in db.scalars(select(User))}
        expected_roles = {"alice": "student", "bob": "student", "carol": "student", "lee": "advisor"}
        # 先验证全部前提，避免默默改变用户角色或写入部分演示数据。
        for username, role in expected_roles.items():
            if username not in users or users[username].role != role:
                raise ValueError(f"Demo user {username!r} must exist with role {role!r}; existing data was not changed.")

        for username, title in DEMO_APPLICATIONS:
            owner_id = users[username].id
            existing = db.scalar(select(Application.id).where(Application.owner_id == owner_id))
            if existing is None:
                db.add(Application(owner_id=owner_id, title=title))
                counts["applications"] += 1

        for username in ("alice", "bob"):
            key = (users["lee"].id, users[username].id)
            if db.get(AdvisorAssignment, key) is None:
                db.add(AdvisorAssignment(advisor_id=key[0], student_id=key[1]))
                counts["assignments"] += 1
    return counts


def main() -> None:
    engine = create_db_engine()
    try:
        counts = seed_applications(engine)
        print(f"Database: {DATABASE_PATH}")
        print(f"Created {counts['applications']} application(s), {counts['assignments']} assignment(s).")
        with Session(engine) as db:
            rows = db.execute(
                select(Application.id, User.username, Application.title)
                .join(User, Application.owner_id == User.id)
                .order_by(Application.id)
            )
            for application_id, owner, title in rows:
                print(f"{application_id}: {title} (owner: {owner})")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
