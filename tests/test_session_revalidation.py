"""Regression checks for session changes while awaiting a model proposal."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select, update
from sqlalchemy.orm import Session

from app.agent.provider import get_agent_provider
from app.agent.schemas import ToolCall
from app.auth.service import COOKIE_NAME, create_login_session, revoke_login_session, token_digest
from app.database.models import Application, AuditLog, LoginSession, User
from app.database.seed import seed_users
from app.database.seed_applications import seed_applications
from app.database.seed_content import seed_content
from app.main import create_app


@pytest.mark.parametrize("change", [
    "logout", "expire", "switch", "rebind", "demote", "logout_audit_failure",
])
def test_revocation_during_model_wait_prevents_delivery(tmp_path, change, monkeypatch):
    with TestClient(create_app(tmp_path / "review.db", encryption_key=b"r" * 32)) as client:
        engine = client.app.state.engine
        seed_users(engine)
        seed_applications(engine)
        seed_content(engine, client.app.state.field_encryption)
        headers = {"X-CSRF-Protection": "1"}
        assert client.post("/auth/login", headers=headers, json={
            "username": "admin", "password": "Admin-demo-2026!",
        }).status_code == 200
        token = client.cookies.get(COOKIE_NAME)
        decrypt_calls = []
        def forbidden_decrypt(*args, **kwargs):
            decrypt_calls.append(True)
            raise AssertionError("Rejected request must not decrypt")
        monkeypatch.setattr(client.app.state.field_encryption, "decrypt", forbidden_decrypt)
        with Session(engine) as db:
            target = db.scalar(select(Application.id).join(User, Application.owner_id == User.id).where(User.username == "bob"))

        class DelayedProvider:
            def propose(self, message):
                # Deterministically commit an independent change after request auth,
                # before the proposal returns. No network, sleeps, or production data.
                with Session(engine) as db:
                    if change in ("logout", "logout_audit_failure"):
                        revoke_login_session(db, token)
                    elif change == "expire":
                        db.execute(update(LoginSession).where(LoginSession.token_hash == token_digest(token)).values(expires_at=0))
                        db.commit()
                    elif change == "switch":
                        bob = db.scalar(select(User).where(User.username == "bob"))
                        create_login_session(db, bob, token)
                    elif change == "rebind":
                        # Defensive identity-binding check, not a public attacker capability.
                        bob = db.scalar(select(User).where(User.username == "bob"))
                        db.execute(update(LoginSession).where(LoginSession.token_hash == token_digest(token)).values(user_id=bob.id))
                        db.commit()
                    else:
                        db.execute(update(User).where(User.username == "admin").values(role="student"))
                        db.commit()
                return ToolCall(tool_name="read_application", arguments={"application_id": target})

        client.app.dependency_overrides[get_agent_provider] = lambda: DelayedProvider()
        statements = []
        def capture(_conn, _cursor, statement, _params, _context, _many):
            statements.append(statement.lower())
            if change == "logout_audit_failure" and statement.lower().startswith("insert into audit_logs"):
                raise RuntimeError("Simulated audit write failure")
        event.listen(engine, "before_cursor_execute", capture)
        try:
            response = client.post("/chat", headers=headers, json={"message": "read target"})
        finally:
            event.remove(engine, "before_cursor_execute", capture)
        body = response.json()
        if change == "logout_audit_failure":
            assert response.status_code == 503
            assert body == {"detail": "Audit logging unavailable"}
            assert not decrypt_calls
            assert not any("application_contents" in sql for sql in statements)
            with Session(engine) as db:
                assert list(db.scalars(select(AuditLog))) == []
            return
        with Session(engine) as db:
            audit = db.scalars(select(AuditLog)).one()
            audit_decision = audit.decision if audit else None
            assert audit.execution_status == "NOT_EXECUTED"
            assert audit.request_id == body["request_id"]
            assert audit.application_id == target
            assert audit.user_id == db.scalar(select(User.id).where(User.username == "admin"))
            assert audit.role == ("student" if change == "demote" else "admin")
        if change in ("logout", "expire", "switch"):
            assert client.get("/auth/me").status_code == 401
        # Output records only status/decisions, never credentials or material body.
        print(f"review change={change} http={response.status_code} decision={body.get('gateway_result', {}).get('decision')} audit={audit_decision}")
        assert response.status_code == (403 if change == "demote" else 401)
        assert body.get("gateway_result", {}).get("data") is None
        assert body["gateway_result"]["decision"] == "DENY"
        assert audit_decision == "DENY"
        assert not decrypt_calls
        assert not any("application_contents" in sql for sql in statements)
