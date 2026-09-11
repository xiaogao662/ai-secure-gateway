"""隐藏输入 DeepSeek 密钥并启动本机服务，不写入文件。"""

import argparse
import os

from scripts.check_gemini import CheckFailed, read_key


def main() -> int:
    parser = argparse.ArgumentParser(description="Start local gateway with DeepSeek enabled; up to 20 model requests per process.")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    try:
        key = read_key(env_name="DEEPSEEK_API_KEY", provider="DeepSeek")
    except CheckFailed as error:
        print(f"FAILED: {error}")
        return 1
    except KeyboardInterrupt:
        return 130
    from app.main import create_app
    import uvicorn

    application = create_app(
        load_encryption_config=True, agent_mode="deepseek", deepseek_api_key=key,
        secure_cookie=os.environ.get("AI_SECURE_COOKIE_SECURE") == "1",
    )
    print("DeepSeek mode: one model request per chat, thinking OFF, output limit 128, total attempt limit 20 per start.")
    print("Per-user limit: 5 admitted chat attempts in the last 60 seconds; rate-limited requests do not call the model.")
    print("Only demo messages and tool definitions go to DeepSeek. Material contents and sessions stay local.")
    uvicorn.run(application, host="127.0.0.1", port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
