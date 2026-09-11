import io
import json
import warnings
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

from scripts import check_gemini as check


FAKE_KEY = "fake-test-key-not-a-real-credential"


class FakeResponse(io.BytesIO):
    status = 200


def fake_transport(monkeypatch, raw):
    calls = []

    class FakeOpener:
        def open(self, request, timeout):
            calls.append((request, timeout))
            if isinstance(raw, Exception):
                raise raw
            return FakeResponse(raw)

    monkeypatch.setattr(check, "build_opener", lambda *handlers: FakeOpener())
    return calls


def successful_response():
    return json.dumps({"candidates": [{"content": {"parts": [{"text": "OK"}]}, "finishReason": "STOP"}]}).encode()


def test_one_small_fixed_request_without_key_in_url_or_body(monkeypatch):
    calls = fake_transport(monkeypatch, successful_response())
    check.check_connection(FAKE_KEY)
    (request, timeout), = calls
    assert request.full_url == check.ENDPOINT and request.get_method() == "POST"
    assert request.get_header("X-goog-api-key") == FAKE_KEY
    assert FAKE_KEY not in request.full_url and FAKE_KEY.encode() not in request.data
    body = json.loads(request.data)
    assert body["contents"] == [{"role": "user", "parts": [{"text": "Reply with exactly OK and nothing else."}]}]
    assert body["generationConfig"]["maxOutputTokens"] == 64
    assert body["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 0}
    assert "tools" not in body and timeout == 20


@pytest.mark.parametrize("status", [301, 400, 401, 403, 404, 429, 500, 503])
def test_http_errors_are_sanitized_and_not_retried(monkeypatch, status):
    error = HTTPError(check.ENDPOINT, status, FAKE_KEY, {}, io.BytesIO(FAKE_KEY.encode()))
    calls = fake_transport(monkeypatch, error)
    with pytest.raises(check.CheckFailed, match=f"HTTP_{status}") as caught:
        check.check_connection(FAKE_KEY)
    assert FAKE_KEY not in str(caught.value)
    assert len(calls) == 1


@pytest.mark.parametrize("error", [URLError(FAKE_KEY), TimeoutError(FAKE_KEY)])
def test_network_error_hides_details(monkeypatch, error):
    calls = fake_transport(monkeypatch, error)
    with pytest.raises(check.CheckFailed, match="NETWORK_ERROR") as caught:
        check.check_connection(FAKE_KEY)
    assert FAKE_KEY not in str(caught.value) and len(calls) == 1


@pytest.mark.parametrize("raw,code", [
    (b"not json", "RESPONSE_INVALID"),
    (b"{}", "RESPONSE_INVALID"),
    (b'{"candidates": []}', "RESPONSE_INVALID"),
    (b"x" * (check.MAX_RESPONSE_BYTES + 1), "RESPONSE_TOO_LARGE"),
    (json.dumps({"candidates": [{"content": {"parts": [{"text": FAKE_KEY}]}, "finishReason": "STOP"}]}).encode(), "RESPONSE_UNEXPECTED"),
    (json.dumps({"candidates": [{"content": {"parts": [{"text": "OK"}]}, "finishReason": "MAX_TOKENS"}]}).encode(), "RESPONSE_UNEXPECTED"),
], ids=["invalid-json", "missing-candidate", "empty-candidates", "oversized", "unexpected-text", "truncated"])
def test_invalid_or_incomplete_responses_are_not_printed(monkeypatch, raw, code):
    fake_transport(monkeypatch, raw)
    with pytest.raises(check.CheckFailed, match=code) as caught:
        check.check_connection(FAKE_KEY)
    assert FAKE_KEY not in str(caught.value)


def test_redirect_handler_refuses_forwarding_key():
    handler = check.NoRedirect()
    request = Request(check.ENDPOINT, headers={"x-goog-api-key": FAKE_KEY})
    assert handler.redirect_request(request, None, 302, "", {}, "https://attacker.example") is None


def test_hidden_input_and_environment_option(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(check.getpass, "getpass", lambda prompt: FAKE_KEY)
    assert check.read_key() == FAKE_KEY
    monkeypatch.setenv("GEMINI_API_KEY", "environment-fake-key")
    assert check.read_key() == "environment-fake-key"


@pytest.mark.parametrize("value", ["", " ", "key\nheader", "密钥", "k" * 2049])
def test_invalid_key_never_reaches_network(monkeypatch, value):
    monkeypatch.setenv("GEMINI_API_KEY", value)
    with pytest.raises(check.CheckFailed, match="INVALID_KEY_INPUT"):
        check.read_key()


def test_no_visible_input_fallback(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    def unavailable(prompt):
        warnings.warn("Cannot hide input", check.getpass.GetPassWarning)
        pytest.fail("Must not continue into visible input")

    monkeypatch.setattr(check.getpass, "getpass", unavailable)
    with pytest.raises(check.CheckFailed, match="INPUT_UNAVAILABLE"):
        check.read_key()


def test_command_success_prints_no_key_or_raw_response(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["check_gemini"])
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    fake_transport(monkeypatch, successful_response())
    assert check.main() == 0
    output = capsys.readouterr().out
    assert "SUCCESS" in output and FAKE_KEY not in output


def test_list_models_is_one_read_only_request_and_filters_output(monkeypatch):
    raw = json.dumps({"models": [
        {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"], "description": FAKE_KEY},
        {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-test-only", "supportedGenerationMethods": ["embedContent"]},
        {"name": "models/gemini-bad\nheader", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-" + FAKE_KEY, "supportedGenerationMethods": ["generateContent"]},
    ], "nextPageToken": "not-printed-token"}).encode()
    calls = fake_transport(monkeypatch, raw)
    assert check.list_models(FAKE_KEY) == (["gemini-2.5-flash"], True)
    (request, timeout), = calls
    assert request.get_method() == "GET" and request.data is None
    assert request.full_url == "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000"
    assert request.get_header("X-goog-api-key") == FAKE_KEY and timeout == 20


@pytest.mark.parametrize("data", [[], {"models": "wrong"}, {"models": [None]}])
def test_list_models_rejects_malformed_metadata(monkeypatch, data):
    fake_transport(monkeypatch, json.dumps(data).encode())
    with pytest.raises(check.CheckFailed, match="RESPONSE_INVALID"):
        check.list_models(FAKE_KEY)


def test_list_cli_never_calls_generation_or_echoes_secret(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["check_gemini", "--list-models"])
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    fake_transport(monkeypatch, json.dumps({"models": [], "nextPageToken": FAKE_KEY}).encode())
    monkeypatch.setattr(check, "check_connection", lambda key: pytest.fail("Do not generate during model listing"))
    assert check.main() == 0
    output = capsys.readouterr().out
    assert "MODEL_LIST_OK" in output and "MORE_PAGES" in output
    assert "NOT_LISTED_ON_THIS_PAGE" in output and FAKE_KEY not in output


def test_list_cli_http_error_is_sanitized(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["check_gemini", "--list-models"])
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    fake_transport(monkeypatch, HTTPError(check.ENDPOINT, 404, FAKE_KEY, {}, io.BytesIO(FAKE_KEY.encode())))
    assert check.main() == 1
    output = capsys.readouterr().out
    assert "HTTP_404" in output and FAKE_KEY not in output


@pytest.mark.parametrize("message,hint", [
    ("models/gemini-2.5-flash is not found for API version v1beta, or is not supported for generateContent.", "MODEL_OR_METHOD_UNAVAILABLE"),
    ("User location is not supported for the API use.", "REGION_RESTRICTION"),
    ("Your API key was reported as leaked.", "KEY_REPORTED_LEAKED"),
    ("API key not valid.", "KEY_REJECTED"),
    ("Please enable billing.", "BILLING_MENTIONED"),
    ("Quota exceeded.", "QUOTA_OR_RATE_LIMIT"),
    ("Permission denied.", "PERMISSION_MENTIONED"),
    ("thinkingBudget parameter not supported.", "GENERATION_PARAMETER_MENTIONED"),
    ("Unrecognized error message", "UNKNOWN"),
])
def test_error_diagnostics_only_expose_fixed_labels(monkeypatch, message, hint):
    body = {"error": {"status": "NOT_FOUND", "message": message + FAKE_KEY, "details": [{"project": "private-project", "key": FAKE_KEY}]}}
    error = HTTPError(check.ENDPOINT, 404, FAKE_KEY, {}, io.BytesIO(json.dumps(body).encode()))
    calls = fake_transport(monkeypatch, error)
    with pytest.raises(check.CheckFailed) as caught:
        check.check_connection(FAKE_KEY)
    output = str(caught.value)
    assert f"format=JSON_ERROR; status=NOT_FOUND; hint={hint}" in output
    assert FAKE_KEY not in output and "private-project" not in output
    assert len(calls) == 1


@pytest.mark.parametrize("body,expected", [
    (b"<html>private diagnostic</html>", "format=HTML"),
    (FAKE_KEY.encode(), "format=NON_JSON"),
    (b"[]", "format=JSON_OTHER"),
    (b"x" * (16 * 1024 + 1), "format=OVERSIZED"),
    (json.dumps({"error": {"status": FAKE_KEY, "message": FAKE_KEY}}).encode(), "status=UNKNOWN"),
    (b'{"error":{"status":[],"message":[]}}', "status=UNKNOWN"),
], ids=["html", "text", "json-other", "oversized", "untrusted-status", "malformed-fields"])
def test_unstructured_error_diagnostics_are_safe(body, expected):
    error = HTTPError(check.ENDPOINT, 404, FAKE_KEY, {}, io.BytesIO(body))
    try:
        output = check.summarize_http_error(error)
    finally:
        error.close()
    assert expected in output and FAKE_KEY not in output and "private diagnostic" not in output


def test_error_body_read_failure_preserves_http_status(monkeypatch):
    class BrokenBody(io.BytesIO):
        def read(self, size=-1):
            raise TimeoutError(FAKE_KEY)

    fake_transport(monkeypatch, HTTPError(check.ENDPOINT, 404, FAKE_KEY, {}, BrokenBody()))
    with pytest.raises(check.CheckFailed, match="HTTP_404") as caught:
        check.check_connection(FAKE_KEY)
    assert "format=UNREADABLE" in str(caught.value) and FAKE_KEY not in str(caught.value)
