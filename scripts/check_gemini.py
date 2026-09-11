"""一次性 Gemini 连通性检查，不导入应用、不接触数据库或材料密钥。"""

import argparse
import getpass
import json
import os
import re
import ssl
import warnings
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


MODEL = "gemini-2.5-flash"
ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
MAX_RESPONSE_BYTES = 64 * 1024


class CheckFailed(Exception):
    """只携带固定的安全诊断信息，不包含密钥或服务商响应正文。"""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # 不允许把携带密钥的请求重定向到其他地址。
        return None


def summarize_http_error(error: HTTPError) -> str:
    """只输出固定分类，不回显服务商的原始 message、details 或响应头。"""
    try:
        raw = error.read(16 * 1024 + 1)
        if len(raw) > 16 * 1024:
            return "format=OVERSIZED; status=UNKNOWN; hint=UNKNOWN"
        try:
            body = json.loads(raw)
        except ValueError:
            kind = "HTML" if raw.lstrip().lower().startswith((b"<!doctype html", b"<html")) else "NON_JSON"
            return f"format={kind}; status=UNKNOWN; hint=UNKNOWN"
        details = body.get("error") if isinstance(body, dict) else None
        if not isinstance(details, dict):
            return "format=JSON_OTHER; status=UNKNOWN; hint=UNKNOWN"
        status = details.get("status")
        allowed_statuses = {
            "INVALID_ARGUMENT", "FAILED_PRECONDITION", "UNAUTHENTICATED", "PERMISSION_DENIED",
            "NOT_FOUND", "RESOURCE_EXHAUSTED", "INTERNAL", "UNAVAILABLE", "DEADLINE_EXCEEDED",
        }
        if not isinstance(status, str) or status not in allowed_statuses:
            status = "UNKNOWN"
        message = details.get("message", "")
        message = message.lower() if isinstance(message, str) else ""
        # 分类仅是原错误文字的线索，不把模糊匹配当作已经证实的根因。
        hint = "UNKNOWN"
        if "api key" in message and "leaked" in message:
            hint = "KEY_REPORTED_LEAKED"
        elif "api key" in message and any(word in message for word in ("invalid", "not valid", "expired")):
            hint = "KEY_REJECTED"
        elif any(word in message for word in ("location", "region", "country")) and any(word in message for word in ("not supported", "unavailable", "not available")):
            hint = "REGION_RESTRICTION"
        elif "billing" in message:
            hint = "BILLING_MENTIONED"
        elif any(word in message for word in ("quota", "rate limit", "resource exhausted")):
            hint = "QUOTA_OR_RATE_LIMIT"
        elif "model" in message and any(word in message for word in ("not found", "not supported", "no longer", "not available", "deprecated")):
            hint = "MODEL_OR_METHOD_UNAVAILABLE"
        elif "permission" in message:
            hint = "PERMISSION_MENTIONED"
        elif any(word in message for word in ("thinkingbudget", "thinkingconfig", "maxoutputtokens", "generationconfig")):
            hint = "GENERATION_PARAMETER_MENTIONED"
        return f"format=JSON_ERROR; status={status}; hint={hint}"
    except (OSError, ValueError, TypeError, HTTPException):
        return "format=UNREADABLE; status=UNKNOWN; hint=UNKNOWN"


def read_key(*, env_name: str = "GEMINI_API_KEY", provider: str = "Gemini") -> str:
    key = os.environ.get(env_name)
    if key is None:
        # 不支持隐藏输入的终端直接停止，避免 getpass 退化成可见输入。
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            try:
                key = getpass.getpass(f"Paste {provider} API key (hidden), then press Enter: ")
            except (getpass.GetPassWarning, EOFError):
                raise CheckFailed("INPUT_UNAVAILABLE: Run this command in an interactive PowerShell terminal.") from None
    key = key.strip()
    if not key or len(key) > 2048 or not all(33 <= ord(char) <= 126 for char in key):
        raise CheckFailed("INVALID_KEY_INPUT: Key is empty or contains invalid characters; check your local input.")
    return key


def request_json(request: Request, *, max_bytes: int = MAX_RESPONSE_BYTES) -> object:
    opener = build_opener(NoRedirect())
    try:
        # 默认验证 HTTPS 证书，使用系统/环境的代理配置；不自动重试。
        with opener.open(request, timeout=20) as response:
            if response.status != 200:
                raise CheckFailed("HTTP_UNEXPECTED: Unexpected HTTP response; no raw response was printed.")
            raw = response.read(max_bytes + 1)
    except HTTPError as error:
        code = error.code
        try:
            diagnostic = summarize_http_error(error)
        finally:
            error.close()
        explanations = {
            400: "Check API key, request compatibility, and region availability.",
            401: "Check API key validity.",
            402: "Insufficient balance; check the provider account before retrying.",
            403: "Check project permissions, key restrictions, and region availability.",
            404: "The selected model or endpoint is unavailable for this request.",
            429: "Rate limit or quota exhausted; inspect provider usage before retrying.",
        }
        explanation = explanations.get(code, "Service returned an error; no automatic retry was performed.")
        raise CheckFailed(f"HTTP_{code}: {explanation}\nDIAGNOSTIC: {diagnostic}") from None
    except (URLError, TimeoutError, OSError, ssl.SSLError, HTTPException):
        raise CheckFailed("NETWORK_ERROR: Check network, DNS, proxy and HTTPS certificates; the request may have timed out.") from None
    if len(raw) > max_bytes:
        raise CheckFailed("RESPONSE_TOO_LARGE: Response exceeded the local safety limit.")
    try:
        return json.loads(raw)
    except ValueError:
        raise CheckFailed("RESPONSE_INVALID: HTTP succeeded, but the response was not valid JSON.") from None


def list_models(key: str) -> tuple[list[str], bool]:
    """只查询一页模型元数据，不发送生成请求；不打印模型描述或原始响应。"""
    request = Request(
        "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000",
        headers={"x-goog-api-key": key}, method="GET",
    )
    data = request_json(request, max_bytes=2 * 1024 * 1024)
    if not isinstance(data, dict) or not isinstance(data.get("models", []), list):
        raise CheckFailed("RESPONSE_INVALID: Expected a model list; raw response was hidden.")
    names = set()
    for item in data.get("models", []):
        if not isinstance(item, dict):
            raise CheckFailed("RESPONSE_INVALID: Invalid model metadata; raw response was hidden.")
        name = item.get("name", "")
        methods = item.get("supportedGenerationMethods", [])
        if (
            isinstance(name, str) and isinstance(methods, list)
            and re.fullmatch(r"models/gemini-[a-z0-9][a-z0-9._-]{0,119}", name)
            and "generateContent" in methods and key not in name
        ):
            names.add(name.removeprefix("models/"))
    return sorted(names), bool(data.get("nextPageToken"))


def check_connection(key: str) -> None:
    payload = {
        "contents": [{"role": "user", "parts": [{"text": "Reply with exactly OK and nothing else."}]}],
        "generationConfig": {
            "maxOutputTokens": 64,
            "temperature": 0,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    request = Request(
        ENDPOINT, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
    )
    data = request_json(request)
    try:
        candidate = data["candidates"][0]
        parts = candidate["content"]["parts"]
        answer = "".join(part.get("text", "") for part in parts if not part.get("thought", False))
        complete = candidate.get("finishReason") == "STOP"
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        raise CheckFailed("RESPONSE_INVALID: HTTP succeeded, but no usable model response was found.") from None
    if not complete or answer.strip() != "OK":
        raise CheckFailed("RESPONSE_UNEXPECTED: HTTP succeeded, but the model did not finish with the expected OK; raw output was hidden.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Make one Gemini request containing only a harmless OK prompt. No database access.")
    parser.add_argument("--list-models", action="store_true", help="List Gemini models advertising generateContent; do not generate text.")
    args = parser.parse_args()
    if args.list_models:
        print("Model-list diagnostic only: one metadata request, no text generation.", flush=True)
    else:
        print(f"Model: {MODEL}. One request, no automatic retries; quota or billing may apply.", flush=True)
    try:
        key = read_key()
        if args.list_models:
            print("Connecting to Google model-list API...", flush=True)
            names, more = list_models(key)
            print("MODEL_LIST_OK: Models advertising generateContent (quota not verified):")
            for name in names:
                print(name)
            if not names:
                print("NO_MATCHING_MODELS: No matching Gemini model was returned on this page.")
            print(f"Configured model {MODEL}: {'LISTED' if MODEL in names else 'NOT_LISTED_ON_THIS_PAGE'}")
            if more:
                print("MORE_PAGES: The list is incomplete; no additional requests were sent.")
            return 0
        print("Connecting to Gemini generation API...", flush=True)
        check_connection(key)
    except CheckFailed as error:
        print(f"FAILED: {error}")
        return 1
    except KeyboardInterrupt:
        print("CANCELLED: No further requests will be made.")
        return 130
    print("SUCCESS: Gemini replied OK. No application data was sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
