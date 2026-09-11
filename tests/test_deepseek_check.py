import io
import json
from urllib.error import HTTPError

import pytest

from scripts import check_deepseek as check
from scripts import check_gemini as transport


KEY = "fake-deepseek-key-not-real"


def result():
    return {"choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 6, "completion_tokens": 1, "total_tokens": 7}}


def test_single_request_has_cost_limits_and_correct_destination(monkeypatch):
    calls = []

    def capture(request):
        calls.append(request)
        return result()

    monkeypatch.setattr(check, "request_json", capture)
    assert check.check_connection(KEY)["total_tokens"] == 7
    request, = calls
    assert request.full_url == "https://api.deepseek.com/chat/completions"
    assert request.get_header("Authorization") == f"Bearer {KEY}"
    assert request.get_header("X-goog-api-key") is None
    assert KEY not in request.full_url and KEY.encode() not in request.data
    assert json.loads(request.data) == {
        "model": "deepseek-v4-flash", "messages": [{"role": "user", "content": "Reply only OK."}],
        "thinking": {"type": "disabled"}, "max_tokens": 16, "temperature": 0, "stream": False,
    }


@pytest.mark.parametrize("data", [{}, {"choices": []}, {"choices": [None]},
    {"choices": [{"message": {"content": " "}, "finish_reason": "stop"}]},
    {"choices": [{"message": {"content": "OK"}, "finish_reason": "length"}]}])
def test_bad_or_truncated_results_do_not_echo_response(monkeypatch, data):
    monkeypatch.setattr(check, "request_json", lambda request: data)
    with pytest.raises(check.CheckFailed) as caught:
        check.check_connection(KEY)
    assert KEY not in str(caught.value)


def test_only_numeric_whitelisted_usage_is_returned(monkeypatch):
    data = result()
    data["usage"] = {"prompt_tokens": True, "completion_tokens": KEY, "total_tokens": -1, "secret": KEY}
    monkeypatch.setattr(check, "request_json", lambda request: data)
    assert check.check_connection(KEY) == {}


def test_deepseek_input_never_uses_gemini_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-fake-key")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    prompts = []

    def hidden_input(prompt):
        prompts.append(prompt)
        return KEY

    monkeypatch.setattr(transport.getpass, "getpass", hidden_input)
    assert check.read_key(env_name="DEEPSEEK_API_KEY", provider="DeepSeek") == KEY
    assert len(prompts) == 1 and "DeepSeek" in prompts[0]


def test_cli_success_prints_usage_not_key(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["check_deepseek"])
    monkeypatch.setenv("DEEPSEEK_API_KEY", KEY)
    monkeypatch.setattr(check, "request_json", lambda request: result())
    assert check.main() == 0
    output = capsys.readouterr().out
    assert "SUCCESS" in output and "total_tokens=7" in output and KEY not in output


@pytest.mark.parametrize("code", [401, 402, 429, 500])
def test_failures_not_retried_and_details_hidden(monkeypatch, code):
    calls = []

    class FailedOpener:
        def open(self, request, timeout):
            calls.append(request)
            raise HTTPError(request.full_url, code, KEY, {}, io.BytesIO(KEY.encode()))

    monkeypatch.setattr(transport, "build_opener", lambda *args: FailedOpener())
    with pytest.raises(check.CheckFailed, match=f"HTTP_{code}") as caught:
        check.check_connection(KEY)
    assert KEY not in str(caught.value) and len(calls) == 1


@pytest.mark.parametrize("content", ["OK.", "好的", KEY])
def test_complete_text_proves_connectivity_without_exact_ok_or_echo(monkeypatch, capsys, content):
    data = result()
    data["choices"][0]["message"]["content"] = content
    monkeypatch.setattr(check, "request_json", lambda request: data)
    monkeypatch.setenv("DEEPSEEK_API_KEY", KEY)
    monkeypatch.setattr("sys.argv", ["check_deepseek"])
    assert check.main() == 0
    output = capsys.readouterr().out
    assert "SUCCESS" in output and content not in output


@pytest.mark.parametrize("finish,expected", [("length", "length"), (KEY, "unknown"), ([], "unknown")])
def test_failure_reports_safe_metadata_and_usage(monkeypatch, finish, expected):
    data = result()
    data["choices"][0] = {"message": {"content": "", "reasoning_content": KEY}, "finish_reason": finish}
    monkeypatch.setattr(check, "request_json", lambda request: data)
    with pytest.raises(check.CheckFailed) as caught:
        check.check_connection(KEY)
    output = str(caught.value)
    assert f"finish_reason={expected}" in output
    assert "reasoning_present=True" in output and "total_tokens=7" in output
    assert KEY not in output
