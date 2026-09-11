import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.auth.service import COOKIE_NAME, SESSION_TTL_SECONDS, token_digest
from app.database.models import LoginSession, User
from app.database.seed import DEMO_USERS, seed_users
from app.main import create_app


CSRF_HEADERS = {"X-CSRF-Protection": "1"}


@pytest.fixture
def client(tmp_path):
    application = create_app(tmp_path / "auth.db")
    with TestClient(application) as test_client:
        seed_users(application.state.engine)
        yield test_client


def login(client, username="alice", password="Alice-demo-2026!", **extra):
    return client.post(
        "/auth/login",
        json={"username": username, "password": password, **extra},
        headers=CSRF_HEADERS,
    )


@pytest.mark.parametrize("username,role,password", DEMO_USERS)
def test_login_and_me_return_only_public_user_fields(client, username, role, password):
    response = login(client, username, password)
    assert response.status_code == 200
    assert set(response.json()) == {"id", "username", "role"}
    assert response.json()["username"] == username
    assert response.json()["role"] == role
    assert password not in response.text
    assert "$argon2" not in response.text
    current_user = client.get("/auth/me")
    assert current_user.status_code == 200
    assert current_user.json() == response.json()
    assert current_user.headers["cache-control"] == "no-store"


def test_cookie_and_database_do_not_contain_client_supplied_identity(client):
    response = login(client)
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert "Path=/" in cookie
    assert f"Max-Age={SESSION_TTL_SECONDS}" in cookie
    token = client.cookies.get(COOKIE_NAME)
    assert len(token) == 43
    with Session(client.app.state.engine) as db:
        stored = db.scalar(select(LoginSession))
        assert stored.token_hash == token_digest(token)
        assert stored.token_hash != token
        assert stored.user_id == response.json()["id"]
        assert int(time.time()) < stored.expires_at <= int(time.time()) + SESSION_TTL_SECONDS
        digest = stored.token_hash
    # 数据库中的摘要本身不能当作登录令牌使用。
    assert client.get("/auth/me", headers={"Cookie": f"{COOKIE_NAME}={digest}"}).status_code == 401


@pytest.mark.parametrize("token", [None, "admin", "a" * 43, "a" * 500])
def test_missing_or_forged_cookie_cannot_authenticate(client, token):
    headers = {} if token is None else {"Cookie": f"{COOKIE_NAME}={token}"}
    response = client.get("/auth/me", headers=headers)
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}
    assert response.headers["cache-control"] == "no-store"


def test_wrong_password_and_unknown_user_have_same_response(client):
    wrong = login(client, password="wrong")
    unknown = login(client, username="missing", password="wrong")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "Invalid username or password"}
    assert COOKIE_NAME not in client.cookies
    with Session(client.app.state.engine) as db:
        assert list(db.scalars(select(LoginSession))) == []


@pytest.mark.parametrize("username", ["alice", "missing"])
def test_login_throttle_precedes_password_check_and_creates_no_session(client, username, monkeypatch):
    from app.auth.rate_limit import LoginRateLimiter
    from app.auth import service
    now = [0.0]
    client.app.state.login_rate_limiter = LoginRateLimiter(clock=lambda: now[0])
    checks = []
    monkeypatch.setattr(service, "verify_password", lambda *args: checks.append(True) or False)
    for _ in range(5):
        assert login(client, username, "wrong").status_code == 401
    blocked = login(client, username, "wrong")
    assert blocked.status_code == 429
    assert blocked.json() == {"detail": "Too many login attempts", "reason_code": "LOGIN_RATE_LIMIT", "retry_after_seconds": 60}
    assert blocked.headers["Retry-After"] == "60"
    assert blocked.headers["Cache-Control"] == "no-store"
    assert "set-cookie" not in blocked.headers
    assert len(checks) == 5
    with Session(client.app.state.engine) as db:
        assert list(db.scalars(select(LoginSession))) == []
    now[0] = 60
    assert login(client, username, "wrong").status_code == 401
    assert len(checks) == 6


def test_login_limit_preserves_existing_session_and_does_not_reset_on_logout(client):
    assert login(client).status_code == 200
    original_token = client.cookies.get(COOKIE_NAME)
    for _ in range(5):
        assert login(client, "bob", "wrong").status_code == 401
    assert login(client, "bob", "Bob-demo-2026!").status_code == 429
    assert client.cookies.get(COOKIE_NAME) == original_token
    assert client.get("/auth/me").json()["username"] == "alice"
    assert client.post("/auth/logout", headers=CSRF_HEADERS).status_code == 200
    assert login(client, "bob", "Bob-demo-2026!").status_code == 429


def test_invalid_login_requests_do_not_consume_password_check_quota(client):
    for _ in range(6):
        assert client.post("/auth/login", json={"username": "alice", "password": "wrong"}).status_code == 403
        assert login(client, role="admin").status_code == 422
    assert login(client).status_code == 200


def test_forged_ip_headers_and_random_names_cannot_bypass_global_login_limit(client, monkeypatch):
    from app.auth import service
    checks = []
    monkeypatch.setattr(service, "verify_password", lambda *args: checks.append(True) or False)
    for i in range(21):
        response = client.post("/auth/login", headers={**CSRF_HEADERS, "X-Forwarded-For": f"192.0.2.{i}", "X-Real-IP": f"192.0.2.{i}"},
                               json={"username": f"missing-{i}", "password": "wrong"})
        assert response.status_code == (401 if i < 20 else 429)
    assert len(checks) == 20


@pytest.mark.parametrize("extra", [{"role": "admin"}, {"user_id": 5}])
def test_login_rejects_supplied_identity_without_echoing_password(client, extra):
    response = login(client, **extra)
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request parameters"}
    assert "Alice-demo-2026!" not in response.text
    assert COOKIE_NAME not in client.cookies


@pytest.mark.parametrize("password", ["", "s" * 129, 123, {"secret": "do-not-echo"}])
def test_invalid_password_input_has_sanitized_error(client, password):
    response = login(client, password=password)
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request parameters"}


def test_identity_query_and_headers_do_not_override_logged_in_user(client):
    login(client)
    response = client.get("/auth/me?user_id=5&role=admin", headers={"X-User-ID": "5", "X-Role": "admin"})
    assert response.status_code == 200
    assert response.json()["username"] == "alice"
    assert response.json()["role"] == "student"


def test_role_is_read_from_database_on_each_request(client):
    login(client)
    with Session(client.app.state.engine) as db, db.begin():
        user = db.scalar(select(User).where(User.username == "alice"))
        user.role = "advisor"
    assert client.get("/auth/me").json()["role"] == "advisor"


def test_expired_session_is_rejected_even_if_cookie_is_sent(client):
    login(client)
    token = client.cookies.get(COOKIE_NAME)
    with Session(client.app.state.engine) as db, db.begin():
        stored = db.get(LoginSession, token_digest(token))
        stored.expires_at = int(time.time())
    assert client.get("/auth/me", headers={"Cookie": f"{COOKIE_NAME}={token}"}).status_code == 401


def test_login_rotates_session_and_switches_user(client):
    login(client)
    old_token = client.cookies.get(COOKIE_NAME)
    assert login(client, "bob", "Bob-demo-2026!").status_code == 200
    assert client.cookies.get(COOKIE_NAME) != old_token
    assert client.get("/auth/me").json()["username"] == "bob"
    assert client.get("/auth/me", headers={"Cookie": f"{COOKIE_NAME}={old_token}"}).status_code == 401
    with Session(client.app.state.engine) as db:
        assert db.get(LoginSession, token_digest(old_token)) is None


def test_logout_revokes_server_session_and_rejects_replay(client):
    login(client)
    token = client.cookies.get(COOKIE_NAME)
    response = client.post("/auth/logout", headers=CSRF_HEADERS)
    assert response.status_code == 200
    assert response.json() == {"status": "logged_out"}
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert COOKIE_NAME not in client.cookies
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers={"Cookie": f"{COOKIE_NAME}={token}"}).status_code == 401
    with Session(client.app.state.engine) as db:
        assert db.get(LoginSession, token_digest(token)) is None
    assert client.post("/auth/logout", headers=CSRF_HEADERS).status_code == 200


def test_logout_does_not_revoke_another_browser_session(client):
    login(client)
    alice_token = client.cookies.get(COOKIE_NAME)
    client.cookies.clear()
    login(client, "bob", "Bob-demo-2026!")
    client.post("/auth/logout", headers=CSRF_HEADERS)
    response = client.get("/auth/me", headers={"Cookie": f"{COOKIE_NAME}={alice_token}"})
    assert response.status_code == 200
    assert response.json()["username"] == "alice"


@pytest.mark.parametrize("endpoint", ["/auth/login", "/auth/logout"])
@pytest.mark.parametrize("headers", [{}, {"X-CSRF-Protection": "0"}, {**CSRF_HEADERS, "Origin": "https://evil.example"}])
def test_auth_writes_require_csrf_header_and_matching_origin(client, endpoint, headers):
    login(client)
    token = client.cookies.get(COOKIE_NAME)
    response = client.post(endpoint, json={"username": "bob", "password": "Bob-demo-2026!"}, headers=headers)
    assert response.status_code == 403
    assert client.get("/auth/me").json()["username"] == "alice"
    assert client.cookies.get(COOKIE_NAME) == token


def test_matching_origin_is_accepted_and_cross_origin_preflight_is_not(client):
    response = client.post(
        "/auth/login",
        json={"username": "alice", "password": "Alice-demo-2026!"},
        headers={**CSRF_HEADERS, "Origin": "http://testserver"},
    )
    assert response.status_code == 200
    preflight = client.options("/auth/logout", headers={
        "Origin": "https://evil.example",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "X-CSRF-Protection",
    })
    assert "access-control-allow-origin" not in preflight.headers


def test_form_login_is_not_accepted(client):
    response = client.post("/auth/login", data={"username": "alice", "password": "Alice-demo-2026!"}, headers=CSRF_HEADERS)
    assert response.status_code == 422
    assert "Alice-demo-2026!" not in response.text


def test_deleting_user_invalidates_session(client):
    login(client)
    with Session(client.app.state.engine) as db, db.begin():
        user = db.scalar(select(User).where(User.username == "alice"))
        db.delete(user)
    assert client.get("/auth/me").status_code == 401
    with Session(client.app.state.engine) as db:
        assert list(db.scalars(select(LoginSession))) == []


def test_session_survives_app_restart_and_secure_cookie_can_be_enabled(tmp_path):
    database_path = tmp_path / "persistent.db"
    with TestClient(create_app(database_path, secure_cookie=True), base_url="https://testserver") as first:
        seed_users(first.app.state.engine)
        response = login(first)
        assert "Secure" in response.headers["set-cookie"]
        token = first.cookies.get(COOKIE_NAME)
        assert first.get("/auth/me").status_code == 200
    with TestClient(create_app(database_path, secure_cookie=True), base_url="https://testserver") as second:
        response = second.get("/auth/me", headers={"Cookie": f"{COOKIE_NAME}={token}"})
        assert response.status_code == 200
        assert response.json()["username"] == "alice"


def test_startup_adds_session_table_without_changing_existing_users(tmp_path):
    from app.database.session import create_db_engine

    path = tmp_path / "previous-stage.db"
    engine = create_db_engine(path)
    User.__table__.create(engine)
    with Session(engine) as db, db.begin():
        db.add(User(username="existing", role="advisor", password_hash="preserve-this-hash"))
    engine.dispose()
    with TestClient(create_app(path)) as test_client:
        assert test_client.get("/health").json() == {"status": "ok"}
        assert "login_sessions" in inspect(test_client.app.state.engine).get_table_names()
        with Session(test_client.app.state.engine) as db:
            users = list(db.scalars(select(User)))
            assert len(users) == 1
            assert (users[0].username, users[0].role, users[0].password_hash) == ("existing", "advisor", "preserve-this-hash")
