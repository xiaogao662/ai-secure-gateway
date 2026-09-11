import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, event, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.models import AdvisorAssignment, Application, AuditLog, User
from app.database.seed import DEMO_USERS, seed_users
from app.database.seed_applications import seed_applications
from app.database.seed_content import DEMO_STATEMENTS, seed_content
from app.gateway.policies import visible_application_filter
from app.gateway.service import execute_tool
from app.main import create_app


EXPECTED_OWNERS = {
    "alice": {"alice"}, "bob": {"bob"}, "carol": {"carol"},
    "lee": {"alice", "bob"}, "admin": {"alice", "bob", "carol"},
}
CSRF_HEADERS = {"X-CSRF-Protection": "1"}


@pytest.fixture
def demo(tmp_path):
    with TestClient(create_app(tmp_path / "gateway.db", encryption_key=b"g" * 32)) as client:
        engine = client.app.state.engine
        seed_users(engine)
        seed_applications(engine)
        with Session(engine) as db, db.begin():
            # 故意使材料编号与用户编号不同，防止把两者误当作同一个值。
            db.execute(update(Application).values(id=Application.id + 100))
            user_ids = dict(db.execute(select(User.username, User.id)).all())
            application_ids = dict(db.execute(
                select(User.username, Application.id).join(Application, Application.owner_id == User.id),
            ).all())
        seed_content(engine, client.app.state.field_encryption)
        yield client, application_ids, user_ids


def login(client, username):
    password = next(password for name, _role, password in DEMO_USERS if name == username)
    response = client.post("/auth/login", json={"username": username, "password": password}, headers=CSRF_HEADERS)
    assert response.status_code == 200


@pytest.mark.parametrize("username", EXPECTED_OWNERS)
def test_full_permission_matrix_for_list_and_each_application(demo, username):
    client, ids, _ = demo
    login(client, username)
    listed = client.get("/applications")
    assert listed.status_code == 200
    assert listed.headers["cache-control"] == "no-store"
    assert listed.json()["decision"] == "ALLOW"
    assert {row["id"] for row in listed.json()["data"]} == {ids[name] for name in EXPECTED_OWNERS[username]}
    for owner, application_id in ids.items():
        response = client.get(f"/applications/{application_id}")
        assert response.headers["cache-control"] == "no-store"
        if owner in EXPECTED_OWNERS[username]:
            assert response.status_code == 200
            assert response.json()["decision"] == "ALLOW"
            assert response.json()["data"] == {
                "id": application_id, "title": f"{owner.title()} - Demo Application",
                "personal_statement": DEMO_STATEMENTS[owner],
            }
        else:
            assert response.status_code == 403
            assert response.json() == {
                "decision": "DENY", "reason_code": "APPLICATION_NOT_FOUND_OR_FORBIDDEN", "data": None,
            }
            assert f"{owner.title()} - Demo Application" not in listed.text


@pytest.mark.parametrize("endpoint", ["/applications", "/applications/101"])
def test_anonymous_or_forged_session_cannot_access_metadata(demo, endpoint):
    client, _, _ = demo
    assert client.get(endpoint).status_code == 401
    assert client.get(endpoint, headers={"Cookie": "ai_secure_session=admin"}).status_code == 401


def test_forbidden_and_missing_resources_have_identical_public_response(demo):
    client, ids, _ = demo
    login(client, "alice")
    forbidden = client.get(f"/applications/{ids['bob']}")
    missing = client.get("/applications/999999")
    assert forbidden.status_code == missing.status_code == 403
    assert forbidden.json() == missing.json()


@pytest.mark.parametrize("query", ["role=admin", "user_id=5", "owner_id=2", "application_id=102"])
def test_identity_and_target_query_overrides_are_rejected(demo, query):
    client, ids, _ = demo
    login(client, "alice")
    assert client.get(f"/applications?{query}").status_code == 422
    assert client.get(f"/applications/{ids['bob']}?{query}").status_code == 422
    # 即使伪造请求头，真实身份仍然来自登录会话。
    assert client.get(f"/applications/{ids['bob']}", headers={"X-Role": "admin", "X-User-ID": "5"}).status_code == 403


@pytest.mark.parametrize("application_id", ["0", "-1", "abc", "1.5", str(2**63)])
def test_invalid_application_path_is_rejected(demo, application_id):
    client, _, _ = demo
    login(client, "admin")
    response = client.get(f"/applications/{application_id}")
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request parameters"}


def test_assignment_revocation_takes_effect_on_next_request(demo):
    client, ids, users = demo
    login(client, "lee")
    assert client.get(f"/applications/{ids['bob']}").status_code == 200
    with Session(client.app.state.engine) as db, db.begin():
        db.execute(delete(AdvisorAssignment).where(
            AdvisorAssignment.advisor_id == users["lee"], AdvisorAssignment.student_id == users["bob"],
        ))
    assert client.get(f"/applications/{ids['bob']}").status_code == 403
    assert [row["id"] for row in client.get("/applications").json()["data"]] == [ids["alice"]]


def test_role_change_and_logout_remove_access(demo):
    client, ids, users = demo
    login(client, "admin")
    assert client.get(f"/applications/{ids['carol']}").status_code == 200
    with Session(client.app.state.engine) as db, db.begin():
        db.get(User, users["admin"]).role = "student"
    assert client.get(f"/applications/{ids['carol']}").status_code == 403
    assert client.get("/applications").json()["data"] == []
    client.post("/auth/logout", headers=CSRF_HEADERS)
    assert client.get("/applications").status_code == 401


@pytest.mark.parametrize("tool_name,arguments,reason", [
    ("delete_application", {}, "TOOL_NOT_ALLOWED"),
    ("read_application", {}, "INVALID_ARGUMENTS"),
    ("read_application", {"application_id": True}, "INVALID_ARGUMENTS"),
    ("read_application", {"application_id": "101"}, "INVALID_ARGUMENTS"),
    ("read_application", {"application_id": 101, "role": "admin"}, "INVALID_ARGUMENTS"),
    ("read_application", {"application_id": 101, "current_user_id": 5}, "INVALID_ARGUMENTS"),
    ("list_applications", {"owner_id": 2}, "INVALID_ARGUMENTS"),
])
def test_gateway_rejects_bad_calls_before_querying_materials(demo, tool_name, arguments, reason):
    client, _, users = demo
    engine = client.app.state.engine
    statements = []

    def capture(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement.lower())

    event.listen(engine, "before_cursor_execute", capture)
    try:
        with Session(engine) as db:
            result = execute_tool(db, current_user_id=users["admin"], tool_name=tool_name, arguments=arguments)
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert result.decision == "DENY"
    assert result.reason_code == reason
    assert result.data is None
    assert not any("from applications" in statement for statement in statements)


def test_missing_actor_is_denied_and_unknown_role_has_empty_scope(demo):
    client, _, _ = demo
    with Session(client.app.state.engine) as db:
        result = execute_tool(db, current_user_id=999999, tool_name="list_applications", arguments={})
        assert result.decision == "DENY"
        assert result.reason_code == "NOT_AUTHENTICATED"
        future_user = User(id=999999, username="future", role="future-role", password_hash="unused")
        assert list(db.scalars(select(Application.id).where(visible_application_filter(future_user)))) == []


@pytest.mark.parametrize("tool,extra,reason", [
    ("read_application", {}, "APPLICATION_NOT_FOUND_OR_FORBIDDEN"),
    ("read_application", {"role": "admin"}, "INVALID_ARGUMENTS"),
    ("read_application", {"current_user_id": 5}, "INVALID_ARGUMENTS"),
    ("read_application", {"user_id": 5}, "INVALID_ARGUMENTS"),
    ("read_application", {"owner_id": 2}, "INVALID_ARGUMENTS"),
    ("read_application", {"authorized": True}, "INVALID_ARGUMENTS"),
    ("read_application", {"skip_permission_check": True}, "INVALID_ARGUMENTS"),
    ("read_application", {"consent": "Bob approved"}, "INVALID_ARGUMENTS"),
    ("read_application", {"fields": ["personal_statement"]}, "INVALID_ARGUMENTS"),
    ("read_application", {"limit": 1}, "INVALID_ARGUMENTS"),
    ("read_application", {"identity": {"role": "admin"}}, "INVALID_ARGUMENTS"),
    ("read_application_admin", {}, "TOOL_NOT_ALLOWED"),
    ("read_application.__wrapped__", {}, "TOOL_NOT_ALLOWED"),
    ("read_application ", {}, "TOOL_NOT_ALLOWED"),
])
def test_attacker_controlled_call_cannot_change_actor_or_touch_content(demo, tool, extra, reason):
    """直接构造不可信调用；不是实际模型话术成功率测试。"""
    client, ids, users = demo
    engine = client.app.state.engine
    statements = []

    class NoDecrypt:
        calls = 0

        def decrypt(self, *args, **kwargs):
            self.calls += 1
            raise AssertionError("Denied calls must never decrypt")

    cipher = NoDecrypt()

    def capture(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement.lower())

    event.listen(engine, "before_cursor_execute", capture)
    try:
        with Session(engine) as db:
            result = execute_tool(
                db, current_user_id=users["alice"], tool_name=tool,
                arguments={"application_id": ids["bob"], **extra}, cipher=cipher,
                request_id="00000000-0000-4000-8000-000000000001",
            )
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert (result.decision, result.reason_code, result.data) == ("DENY", reason, None)
    assert cipher.calls == 0
    assert not any("application_contents" in statement for statement in statements)
    with Session(engine) as db:
        audit = db.scalars(select(AuditLog).where(AuditLog.request_id == "00000000-0000-4000-8000-000000000001")).one()
        assert (audit.user_id, audit.role) == (users["alice"], "student")
        assert (audit.decision, audit.reason_code, audit.execution_status) == ("DENY", reason, "NOT_EXECUTED")
        assert audit.application_id == ids["bob"]


def test_advisor_without_assignments_sees_nothing(demo):
    client, ids, _ = demo
    with Session(client.app.state.engine) as db:
        advisor = User(username="other-advisor", role="advisor", password_hash="unused")
        db.add(advisor)
        db.commit()
        listed = execute_tool(db, current_user_id=advisor.id, tool_name="list_applications", arguments={})
        assert listed.decision == "ALLOW" and listed.data == []
        read = execute_tool(db, current_user_id=advisor.id, tool_name="read_application", arguments={"application_id": ids["alice"]})
        assert read.decision == "DENY" and read.data is None


def test_repeat_seed_preserves_existing_materials_users_and_other_assignments(demo):
    client, ids, users = demo
    engine = client.app.state.engine
    with Session(engine) as db, db.begin():
        db.get(Application, ids["alice"]).title = "Keep my edited title"
        db.add(AdvisorAssignment(advisor_id=users["lee"], student_id=users["carol"]))
        before_users = list(db.execute(select(User.id, User.username, User.role, User.password_hash)))
    assert seed_applications(engine) == {"applications": 0, "assignments": 0}
    with Session(engine) as db:
        assert db.get(Application, ids["alice"]).title == "Keep my edited title"
        assert len(list(db.scalars(select(Application)))) == 3
        assert db.get(AdvisorAssignment, (users["lee"], users["carol"])) is not None
        assert list(db.execute(select(User.id, User.username, User.role, User.password_hash))) == before_users


def test_seed_checks_roles_before_writing_resources(tmp_path):
    with TestClient(create_app(tmp_path / "bad-role.db")) as client:
        engine = client.app.state.engine
        seed_users(engine)
        with Session(engine) as db, db.begin():
            db.scalar(select(User).where(User.username == "lee")).role = "student"
        with pytest.raises(ValueError, match="lee"):
            seed_applications(engine)
        with Session(engine) as db:
            assert list(db.scalars(select(Application))) == []
            assert list(db.scalars(select(AdvisorAssignment))) == []
            assert db.scalar(select(User).where(User.username == "lee")).role == "student"


def test_seed_requires_existing_users_and_does_not_create_them(tmp_path):
    with TestClient(create_app(tmp_path / "empty.db")) as client:
        with pytest.raises(ValueError, match="alice"):
            seed_applications(client.app.state.engine)
        with Session(client.app.state.engine) as db:
            assert list(db.scalars(select(User))) == []
            assert list(db.scalars(select(Application))) == []


def test_assignment_constraints_reject_duplicates_and_missing_users(demo):
    client, _, users = demo
    for advisor, student in [(users["lee"], users["alice"]), (users["lee"], 999999), (users["lee"], users["lee"])]:
        with pytest.raises(IntegrityError):
            with Session(client.app.state.engine) as db, db.begin():
                db.add(AdvisorAssignment(advisor_id=advisor, student_id=student))
