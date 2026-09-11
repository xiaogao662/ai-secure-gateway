"""单次低用量连接检查，不接数据库，也不接入聊天接口。"""

import argparse
import json
from urllib.request import Request

# 复用已有隐藏输入、HTTPS 与安全错误处理；导入不会运行 Gemini 检查。
from scripts.check_gemini import CheckFailed, read_key, request_json


MODEL = "deepseek-v4-flash"
ENDPOINT = "https://api.deepseek.com/chat/completions"


def safe_usage(data: dict) -> dict[str, int]:
    usage = data.get("usage", {})
    if not isinstance(usage, dict):
        return {}
    return {
        name: usage[name] for name in ("prompt_tokens", "completion_tokens", "total_tokens")
        if type(usage.get(name)) is int and 0 <= usage[name] <= 10**9
    }


def check_connection(key: str) -> dict[str, int]:
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "Reply only OK."}],
        "thinking": {"type": "disabled"},
        "max_tokens": 16,
        "temperature": 0,
        "stream": False,
    }
    request = Request(
        ENDPOINT, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    data = request_json(request)
    try:
        choice = data["choices"][0]
        answer = choice["message"]["content"]
        finish = choice["finish_reason"]
    except (KeyError, IndexError, TypeError):
        raise CheckFailed("RESPONSE_INVALID: No usable model response; raw output was hidden.") from None
    usage = safe_usage(data)
    if finish != "stop" or not isinstance(answer, str) or not answer.strip():
        # 只显示固定结束状态与数字，不打印内容、思考文本或未知状态字符串。
        safe_finish = finish if isinstance(finish, str) and finish in (
            "stop", "length", "content_filter", "tool_calls", "insufficient_system_resource",
        ) else "unknown"
        chars = len(answer) if isinstance(answer, str) else 0
        reasoning_present = bool(choice["message"].get("reasoning_content"))
        usage_text = ", ".join(f"{name}={value}" for name, value in usage.items()) or "unavailable"
        raise CheckFailed(
            "RESPONSE_UNEXPECTED: No complete nonempty text response. No retry.\n"
            f"DIAGNOSTIC: finish_reason={safe_finish}; content_chars={chars}; reasoning_present={reasoning_present}\n"
            f"USAGE: {usage_text}"
        )
    return usage


def main() -> int:
    parser = argparse.ArgumentParser(description="One low-token DeepSeek check: no thinking, output limit 16, no retries or application data.")
    parser.parse_args()
    print(f"Model: {MODEL}. One paid/quota request; thinking OFF, output limit 16 tokens, no retries.", flush=True)
    try:
        key = read_key(env_name="DEEPSEEK_API_KEY", provider="DeepSeek")
        print("Connecting to DeepSeek...", flush=True)
        usage = check_connection(key)
    except CheckFailed as error:
        print(f"FAILED: {error}")
        return 1
    except KeyboardInterrupt:
        print("CANCELLED: No further requests will be made.")
        return 130
    print("SUCCESS: DeepSeek returned a complete text response. Content hidden; no application data sent.")
    if usage:
        print("USAGE: " + ", ".join(f"{name}={value}" for name, value in usage.items()))
    else:
        print("USAGE: Not provided; check the provider console. This does not mean zero usage.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
