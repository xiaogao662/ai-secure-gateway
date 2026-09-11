from datetime import datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.auth.service import COOKIE_NAME
from app.database.models import Application, AuditLog, User
from app.database.seed import DEMO_USERS, seed_users
from app.database.seed_applications import seed_applications
from app.database.seed_content import DEMO_STATEMENTS, seed_content
from app.gateway import service as gateway_service
from app.main import create_app


HEADERS = {"X-CSRF-Protection": "1"}


@pytest.fixture
def demo(tmp_path):
    path = tmp_path / "audit.db"
    with TestClient(create_app(path, encryption_key=b"a" * 32)) as client:
        engine = client.app.state.engine
        seed_users(engine)
        seed_applications(engine)
        seed_content(engine, client.app.state.field_encryption)
        with Session(engine) as db:
            ids = dict(db.execute(select(User.username, User.id)).all())
            materials = dict(db.execute(select(User.username, Application.id).join(Application, Application.owner_id == User.id)).all())
        yield client, ids, materials, path


def login(client, name):
    password = next(password for username, _role, password in DEMO_USERS if username == name)
    assert client.post("/auth/login", json={"username": name, "password": password}, headers=HEADERS).status_code == 200


def logs(client):
    with Session(client.app.state.engine) as db:
        return list(db.scalars(select(AuditLog).order_by(AuditLog.id)))


def test_allow_deny_and_list_each_have_one_durable_correlated_event(demo):
    client, users, materials, _ = demo
    login(client, "alice")
    allow = client.get(f"/applications/{materials['alice']}", headers={"X-Request-ID": "attacker-chosen-id"})
    deny = client.get(f"/applications/{materials['bob']}")
    listed = client.get("/applications")
    assert (allow.status_code, deny.status_code, listed.status_code) == (200, 403, 200)
    entries = logs(client)
    assert len(entries) == 3
    assert [(row.decision, row.execution_status) for row in entries] == [
        ("ALLOW", "SUCCESS"), ("DENY", "NOT_EXECUTED"), ("ALLOW", "SUCCESS"),
    ]
    assert [row.application_id for row in entries] == [materials["alice"], materials["bob"], None]
    for response, row in zip((allow, deny, listed), entries):
        assert row.request_id == response.headers["x-request-id"]
        assert str(UUID(row.request_id)) == row.request_id
        assert row.user_id == users["alice"] and row.role == "student"
        assert datetime.fromisoformat(row.timestamp).utcoffset().total_seconds() == 0
    assert len({row.request_id for row in entries}) == 3


@pytest.mark.parametrize("name", ["alice", "bob", "carol", "lee"])
def test_non_admin_cannot_read_logs_even_with_forged_role(demo, name):
    client, _, _, _ = demo
    login(client, name)
    response = client.get("/audit/logs?role=admin&user_id=5", headers={"X-Role": "admin"})
    assert response.status_code == 403
    assert response.json() == {"detail": "Admin access required"}
    assert response.headers["cache-control"] == "no-store"


def test_admin_listing_is_newest_first_bounded_and_read_only(demo):
    client, _, materials, _ = demo
    assert client.get("/audit/logs").status_code == 401
    login(client, "alice")
    for path in ("/applications", f"/applications/{materials['alice']}", f"/applications/{materials['bob']}"):
        client.get(path)
    login(client, "admin")
    response = client.get("/audit/logs?limit=2&offset=1")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert [row["id"] for row in response.json()] == [2, 1]
    assert len(logs(client)) == 3  # 查看日志不生成一条新的材料访问记录。
    assert client.get("/audit/logs?limit=101").status_code == 422
    assert client.get("/audit/logs?offset=-1").status_code == 422
    assert client.delete("/audit/logs").status_code == 405
    assert client.post("/audit/logs", json={"decision": "ALLOW"}, headers=HEADERS).status_code == 405
    assert len(logs(client)) == 3


@pytest.mark.parametrize("path", ["/applications", "/applications/2"])
def test_anonymous_rejection_is_logged_without_claimed_identity(demo, path):
    client, _, _, _ = demo
    response = client.get(path, headers={"Cookie": "ai_secure_session=admin", "X-User-ID": "5", "X-Role": "admin"})
    assert response.status_code == 401
    entries = logs(client)
    assert len(entries) == 1
    assert entries[0].user_id is None and entries[0].role is None
    assert entries[0].decision == "DENY" and entries[0].reason_code == "NOT_AUTHENTICATED"
    assert entries[0].request_id == response.headers["x-request-id"]


@pytest.mark.parametrize("path,target", [
    ("/applications?role=admin", None),
    ("/applications/2?user_id=5", 2),
    ("/applications/not-a-number", None),
    (f"/applications/{2**80}", None),
])
def test_rejected_parameters_are_logged_without_raw_input(demo, path, target):
    client, users, _, _ = demo
    login(client, "alice")
    response = client.get(path)
    assert response.status_code == 422
    entries = logs(client)
    assert len(entries) == 1
    assert entries[0].user_id == users["alice"]
    assert entries[0].application_id == target
    assert entries[0].decision == "DENY"
    assert entries[0].reason_code == "INVALID_ARGUMENTS"
    assert entries[0].execution_status == "NOT_EXECUTED"


def test_direct_gateway_calls_are_audited_and_do_not_log_attack_text(demo):
    client, users, _, _ = demo
    with Session(client.app.state.engine) as db:
        result = gateway_service.execute_tool(
            db, current_user_id=users["alice"], tool_name="unknown\nSECRET_TOOL_TEXT",
            arguments={"password": "SECRET_PASSWORD", "application_id": "SECRET_TARGET"},
        )
        assert result.decision == "DENY"
        result = gateway_service.execute_tool(
            db, current_user_id=users["alice"], tool_name="read_application",
            arguments={"application_id": 2, "role": "admin", "password": "SECRET_PASSWORD"},
        )
        assert result.reason_code == "INVALID_ARGUMENTS"
    entries = logs(client)
    assert len(entries) == 2
    assert entries[0].tool_name == "unknown_tool" and entries[0].application_id is None
    assert entries[1].user_id == users["alice"] and entries[1].role == "student"
    login(client, "admin")
    text = client.get("/audit/logs").text
    assert "SECRET_" not in text
    assert "unknown\\n" not in text


def test_logs_contain_no_credentials_session_token_or_material_title(demo):
    client, _, materials, _ = demo
    with Session(client.app.state.engine) as db, db.begin():
        db.get(Application, materials["alice"]).title = "CONFIDENTIAL_TITLE_SENTINEL"
    login(client, "alice")
    token = client.cookies.get(COOKIE_NAME)
    assert client.get(f"/applications/{materials['alice']}").status_code == 200
    login(client, "admin")
    response = client.get("/audit/logs")
    for secret in [token, "CONFIDENTIAL_TITLE_SENTINEL", "$argon2", "Alice-demo-2026!", "Admin-demo-2026!", DEMO_STATEMENTS["alice"]]:
        assert secret not in response.text
    assert set(response.json()[0]) == {
        "id", "timestamp", "request_id", "user_id", "role", "tool_name", "application_id",
        "decision", "reason_code", "execution_status",
    }


@pytest.mark.parametrize("logged_in", [True, False])
def test_actual_audit_insert_failure_returns_503_without_material_data(demo, logged_in):
    client, _, materials, _ = demo
    if logged_in:
        login(client, "alice")
    engine = client.app.state.engine

    def fail_insert(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("INSERT INTO AUDIT_LOGS"):
            raise RuntimeError("SIMULATED_STORAGE_SECRET")

    event.listen(engine, "before_cursor_execute", fail_insert)
    try:
        response = client.get(f"/applications/{materials['alice']}")
    finally:
        event.remove(engine, "before_cursor_execute", fail_insert)
    assert response.status_code == 503
    assert response.json() == {"detail": "Audit logging unavailable"}
    assert "SIMULATED_STORAGE_SECRET" not in response.text
    assert "Demo Application" not in response.text
    assert logs(client) == []
    # 故障解除后不残留坏事务；可以正常返回并写入一条日志。
    login(client, "alice")
    assert client.get("/applications").status_code == 200
    assert len(logs(client)) == 1


def test_gateway_error_is_logged_separately_without_exception_text(demo, monkeypatch):
    client, _, materials, _ = demo
    login(client, "alice")

    def fail_tool(*_args, **_kwargs):
        raise RuntimeError("INTERNAL_SECRET_DETAIL")

    monkeypatch.setattr(gateway_service, "_execute_application_tool", fail_tool)
    response = client.get(f"/applications/{materials['alice']}")
    assert response.status_code == 503
    assert response.json() == {"detail": "Gateway execution failed"}
    entries = logs(client)
    assert len(entries) == 1
    assert entries[0].decision == "DENY"
    assert entries[0].reason_code == "GATEWAY_ERROR"
    assert entries[0].execution_status == "ERROR"


def test_role_snapshot_survives_user_changes_and_app_restart(demo):
    client, users, materials, path = demo
    login(client, "lee")
    client.get(f"/applications/{materials['alice']}")
    with Session(client.app.state.engine) as db, db.begin():
        lee = db.get(User, users["lee"])
        lee.role = "student"
        db.flush()
        db.delete(lee)
    entries = logs(client)
    assert len(entries) == 1
    assert entries[0].role == "advisor" and entries[0].user_id == users["lee"]
    with TestClient(create_app(path)) as restarted:
        login(restarted, "admin")
        response = restarted.get("/audit/logs")
        assert response.status_code == 200
        assert response.json()[0]["request_id"] == entries[0].request_id


def test_admin_role_is_checked_again_after_demotion(demo):
    client, users, _, _ = demo
    login(client, "admin")
    assert client.get("/audit/logs").status_code == 200
    with Session(client.app.state.engine) as db, db.begin():
        db.get(User, users["admin"]).role = "student"
    assert client.get("/audit/logs").status_code == 403
