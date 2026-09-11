import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "web.db")) as client:
        yield client


@pytest.mark.parametrize("path", ["/", "/static/app.js", "/static/style.css", "/static/layout.css"])
def test_public_assets_have_browser_protection(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"


def test_config_only_exposes_display_information(client):
    response = client.get("/ui/config")
    assert response.json() == {"mode": "mock", "version": "0.8.0"}
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/auth/me").status_code == 401


@pytest.mark.parametrize("path", ["/static/../main.py", "/static/%2e%2e/main.py", "/static/.secrets/application.key", "/static/data/ai_secure.db"])
def test_static_mount_does_not_serve_private_files(client, path):
    assert client.get(path).status_code == 404


def test_swagger_keeps_its_existing_assets(client):
    response = client.get("/docs")
    assert response.status_code == 200
    assert "content-security-policy" not in response.headers


def test_home_explains_assistant_scope_and_unrelated_question_cost(client):
    response = client.get("/")
    assert "仅支持材料查询，不提供通用聊天" in response.text
    assert "无关问题也可能消耗额度" in response.text
    assert 'aria-describedby="assistant-scope cost-note"' in response.text
    assert "无关问题也可能消耗额度" in client.get("/static/app.js").text


def test_home_has_explicit_copy_action_disabled_without_result(client):
    html = client.get("/").text
    assert 'id="copy-request-id" type="button" disabled' in html
    assert 'id="copy-status"' in html
    assert 'id="decision-help"' in html
