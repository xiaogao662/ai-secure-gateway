import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password, verify_password
from app.database import seed
from app.database.models import Base, User
from app.database.session import create_db_engine


@pytest.fixture
def engine(tmp_path):
    # 每个测试使用独立临时数据库，不接触本地演示账户。
    database_engine = create_db_engine(tmp_path / "test.db")
    Base.metadata.create_all(database_engine)
    yield database_engine
    database_engine.dispose()


def test_seed_creates_expected_users_with_hashed_passwords(engine):
    assert seed.seed_users(engine) == ["alice", "bob", "carol", "lee", "admin"]
    with Session(engine) as session:
        users = {user.username: user for user in session.scalars(select(User))}
        assert len(users) == 5
        for username, role, password in seed.DEMO_USERS:
            user = users[username]
            assert user.role == role
            assert user.password_hash.startswith("$argon2id$")
            assert user.password_hash != password
            assert verify_password(password, user.password_hash)
    columns = {column["name"] for column in inspect(engine).get_columns("users")}
    assert columns == {"id", "username", "role", "password_hash"}


def test_seeding_again_preserves_ids_roles_and_passwords(engine):
    seed.seed_users(engine)
    changed_hash = hash_password("changed-test-password")
    with Session(engine) as session, session.begin():
        alice = session.scalar(select(User).where(User.username == "alice"))
        alice.role = "advisor"
        alice.password_hash = changed_hash
    with Session(engine) as session:
        before = list(session.execute(select(User.id, User.username, User.role, User.password_hash)))
    assert seed.seed_users(engine) == []
    with Session(engine) as session:
        after = list(session.execute(select(User.id, User.username, User.role, User.password_hash)))
    assert after == before


def test_seed_fills_only_missing_users(engine):
    saved_hash = hash_password("existing-account-password")
    with Session(engine) as session, session.begin():
        session.add(User(username="alice", role="student", password_hash=saved_hash))
    assert seed.seed_users(engine) == ["bob", "carol", "lee", "admin"]
    with Session(engine) as session:
        alice = session.scalar(select(User).where(User.username == "alice"))
        assert alice.password_hash == saved_hash


def test_duplicate_username_is_rejected_by_database(engine):
    with Session(engine) as session, session.begin():
        session.add(User(username="alice", role="student", password_hash="test-placeholder"))
    with pytest.raises(IntegrityError):
        with Session(engine) as session, session.begin():
            session.add(User(username="alice", role="admin", password_hash="test-placeholder"))


def test_unknown_role_is_rejected_by_database(engine):
    with pytest.raises(IntegrityError):
        with Session(engine) as session, session.begin():
            session.add(User(username="mallory", role="superadmin", password_hash="test-placeholder"))


def test_failed_seed_does_not_leave_partial_users(engine, monkeypatch):
    calls = 0

    def fail_on_second_password(password):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("Simulated hashing failure")
        return hash_password(password)

    monkeypatch.setattr(seed, "hash_password", fail_on_second_password)
    with pytest.raises(RuntimeError, match="Simulated hashing failure"):
        seed.seed_users(engine)
    with Session(engine) as session:
        assert list(session.scalars(select(User))) == []


def test_password_verification_and_random_salt():
    password = "same-test-password"
    first = hash_password(password)
    second = hash_password(password)
    assert first != second
    assert verify_password(password, first)
    assert verify_password(password, second)
    assert not verify_password("wrong-password", first)


@pytest.mark.parametrize("broken_hash", ["", "not-a-hash", "$argon2id$broken"])
def test_broken_hash_is_rejected(broken_hash):
    assert not verify_password("test-password", broken_hash)
