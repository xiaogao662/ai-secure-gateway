import base64

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from app.crypto.field_encryption import ContentAccessError, FieldEncryption
from app.crypto.keys import KeyConfigurationError, create_local_key, decode_key, load_configured_key
from app.database.models import Application, ApplicationContent, AuditLog, User
from app.database.seed import seed_users
from app.database.seed_applications import seed_applications
from app.database.seed_content import DEMO_STATEMENTS, initialize_demo_content, seed_content
from app.main import create_app


TEST_KEY = b"e" * 32  # 只用于独立临时测试数据库，不是本地演示密钥。
HEADERS = {"X-CSRF-Protection": "1"}


@pytest.fixture
def demo(tmp_path):
    path = tmp_path / "encrypted.db"
    with TestClient(create_app(path, encryption_key=TEST_KEY)) as client:
        engine = client.app.state.engine
        seed_users(engine)
        seed_applications(engine)
        seed_content(engine, client.app.state.field_encryption)
        with Session(engine) as db:
            ids = dict(db.execute(select(User.username, Application.id).join(Application, Application.owner_id == User.id)).all())
        yield client, ids, path


def login(client):
    assert client.post("/auth/login", json={"username": "alice", "password": "Alice-demo-2026!"}, headers=HEADERS).status_code == 200


def test_roundtrip_and_fresh_nonces_for_same_plaintext():
    cipher = FieldEncryption(TEST_KEY)
    first = cipher.encrypt("中文 secret", application_id=11, owner_id=2)
    second = cipher.encrypt("中文 secret", application_id=11, owner_id=2)
    assert first[0] != second[0] and first[1] != second[1]
    assert len(first[0]) == 12
    assert len(first[1]) == len("中文 secret".encode()) + 16
    assert cipher.decrypt(*first, application_id=11, owner_id=2) == "中文 secret"


@pytest.mark.parametrize("changed", ["ciphertext", "nonce", "short_nonce", "key", "application_id", "owner_id"])
def test_tamper_wrong_key_and_record_swapping_are_rejected(changed):
    cipher = FieldEncryption(TEST_KEY)
    nonce, ciphertext = cipher.encrypt("secret body", application_id=11, owner_id=2)
    application_id, owner_id = 11, 2
    if changed == "ciphertext":
        ciphertext = bytes([ciphertext[0] ^ 1]) + ciphertext[1:]
    elif changed == "nonce":
        nonce = bytes([nonce[0] ^ 1]) + nonce[1:]
    elif changed == "short_nonce":
        nonce = nonce[:-1]
    elif changed == "key":
        cipher = FieldEncryption(b"x" * 32)
    elif changed == "application_id":
        application_id = 12
    else:
        owner_id = 3
    with pytest.raises(ContentAccessError, match="DECRYPTION_FAILED"):
        cipher.decrypt(nonce, ciphertext, application_id=application_id, owner_id=owner_id)


@pytest.mark.parametrize("encoded", ["", "not valid base64!", base64.b64encode(b"short").decode()])
def test_invalid_configured_keys_are_rejected(encoded):
    with pytest.raises(KeyConfigurationError):
        decode_key(encoded)


def test_key_file_is_reused_and_explicit_bad_environment_does_not_fall_back(tmp_path, monkeypatch):
    path = tmp_path / "secrets" / "application.key"
    monkeypatch.delenv("AI_SECURE_DATA_KEY", raising=False)
    assert load_configured_key(path) is None
    first = create_local_key(path)
    assert len(first) == 32
    assert create_local_key(path) == first
    assert load_configured_key(path) == first
    monkeypatch.setenv("AI_SECURE_DATA_KEY", base64.b64encode(TEST_KEY).decode())
    assert load_configured_key(path) == TEST_KEY
    monkeypatch.setenv("AI_SECURE_DATA_KEY", "invalid")
    with pytest.raises(KeyConfigurationError):
        load_configured_key(path)


def test_sqlite_stores_only_ciphertext_and_read_returns_authorized_plaintext(demo):
    client, ids, path = demo
    login(client)
    response = client.get(f"/applications/{ids['alice']}")
    assert response.status_code == 200
    assert response.json()["data"]["personal_statement"] == DEMO_STATEMENTS["alice"]
    assert "nonce" not in response.text and "ciphertext" not in response.text
    columns = {column["name"] for column in inspect(client.app.state.engine).get_columns("application_contents")}
    assert columns == {"application_id", "nonce", "ciphertext"}
    with Session(client.app.state.engine) as db:
        contents = list(db.scalars(select(ApplicationContent)))
        assert len(contents) == 3 and len({row.nonce for row in contents}) == 3
        assert all(isinstance(row.ciphertext, bytes) and len(row.nonce) == 12 for row in contents)
    database_bytes = path.read_bytes()
    assert all(body.encode() not in database_bytes for body in DEMO_STATEMENTS.values())
    assert TEST_KEY not in database_bytes


def test_list_anonymous_and_forbidden_requests_never_fetch_ciphertext_or_decrypt(demo, monkeypatch):
    client, ids, _ = demo
    engine = client.app.state.engine
    statements = []
    calls = []

    def forbidden_decrypt(*args, **kwargs):
        calls.append(True)
        raise AssertionError("Unauthorized decryption")

    def capture(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement.lower())

    monkeypatch.setattr(client.app.state.field_encryption, "decrypt", forbidden_decrypt)
    event.listen(engine, "before_cursor_execute", capture)
    try:
        assert client.get(f"/applications/{ids['alice']}").status_code == 401
        login(client)
        listed = client.get("/applications")
        assert listed.status_code == 200
        assert all(set(row) == {"id", "title"} for row in listed.json()["data"])
        assert client.get(f"/applications/{ids['bob']}").status_code == 403
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert calls == []
    assert not any("application_contents" in statement for statement in statements)


@pytest.mark.parametrize("failure,reason", [
    ("tamper", "DECRYPTION_FAILED"), ("wrong_key", "DECRYPTION_FAILED"),
    ("missing_key", "ENCRYPTION_NOT_CONFIGURED"), ("missing_content", "CONTENT_NOT_INITIALIZED"),
])
def test_authorized_content_failures_have_no_plaintext_and_audited_error(demo, failure, reason):
    client, ids, _ = demo
    login(client)
    if failure == "missing_key":
        client.app.state.field_encryption = None
    elif failure == "wrong_key":
        client.app.state.field_encryption = FieldEncryption(b"w" * 32)
    else:
        with Session(client.app.state.engine) as db, db.begin():
            row = db.get(ApplicationContent, ids["alice"])
            if failure == "tamper":
                row.ciphertext = bytes([row.ciphertext[0] ^ 1]) + row.ciphertext[1:]
            else:
                db.delete(row)
    response = client.get(f"/applications/{ids['alice']}")
    assert response.status_code == 503
    assert response.json() == {"detail": "Application content unavailable"}
    assert DEMO_STATEMENTS["alice"] not in response.text
    with Session(client.app.state.engine) as db:
        row = db.scalar(select(AuditLog).where(AuditLog.request_id == response.headers["x-request-id"]))
        assert (row.decision, row.reason_code, row.execution_status) == ("ALLOW", reason, "ERROR")
    # 对无权访问者仍然只返回权限拒绝，不泄露密钥/正文的配置状态。
    assert client.get(f"/applications/{ids['bob']}").status_code == 403
    assert client.get("/applications").status_code == 200


def test_repeat_seed_preserves_ciphertext_and_wrong_key_cannot_overwrite(demo):
    client, _, _ = demo
    engine = client.app.state.engine
    with Session(engine) as db:
        before = list(db.execute(select(ApplicationContent.application_id, ApplicationContent.nonce, ApplicationContent.ciphertext)))
    assert seed_content(engine, client.app.state.field_encryption) == 0
    with pytest.raises(ContentAccessError):
        seed_content(engine, FieldEncryption(b"wrong-key".ljust(32, b"!")))
    with Session(engine) as db:
        after = list(db.execute(select(ApplicationContent.application_id, ApplicationContent.nonce, ApplicationContent.ciphertext)))
    assert before == after


def test_missing_key_with_existing_ciphertext_does_not_generate_replacement(demo, tmp_path, monkeypatch):
    client, _, _ = demo
    monkeypatch.delenv("AI_SECURE_DATA_KEY", raising=False)
    missing_file = tmp_path / "lost-key" / "application.key"
    with pytest.raises(KeyConfigurationError, match="restore the original key"):
        initialize_demo_content(client.app.state.engine, missing_file)
    assert not missing_file.exists()


def test_initialization_creates_key_once_and_does_not_rewrite_existing_rows(tmp_path, monkeypatch):
    monkeypatch.delenv("AI_SECURE_DATA_KEY", raising=False)
    key_file = tmp_path / "secrets" / "application.key"
    with TestClient(create_app(tmp_path / "init.db")) as client:
        engine = client.app.state.engine
        seed_users(engine)
        seed_applications(engine)
        assert initialize_demo_content(engine, key_file) == 3
        key = load_configured_key(key_file)
        assert initialize_demo_content(engine, key_file) == 0
        assert load_configured_key(key_file) == key


def test_initialization_failure_does_not_leave_partial_ciphertext(tmp_path, monkeypatch):
    cipher = FieldEncryption(TEST_KEY)
    original_encrypt = cipher.encrypt
    calls = 0

    def fail_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("Encryption failed")
        return original_encrypt(*args, **kwargs)

    monkeypatch.setattr(cipher, "encrypt", fail_second)
    with TestClient(create_app(tmp_path / "rollback.db")) as client:
        engine = client.app.state.engine
        seed_users(engine)
        seed_applications(engine)
        with pytest.raises(RuntimeError):
            seed_content(engine, cipher)
        with Session(engine) as db:
            assert list(db.scalars(select(ApplicationContent))) == []


def test_restart_reuses_key_and_read_does_not_reencrypt(demo):
    client, ids, path = demo
    with Session(client.app.state.engine) as db:
        before = db.get(ApplicationContent, ids["alice"]).ciphertext
    with TestClient(create_app(path, encryption_key=TEST_KEY)) as restarted:
        login(restarted)
        assert restarted.get(f"/applications/{ids['alice']}").json()["data"]["personal_statement"] == DEMO_STATEMENTS["alice"]
    with Session(client.app.state.engine) as db:
        assert db.get(ApplicationContent, ids["alice"]).ciphertext == before
