# DeepSeek：低用量连接测试

在项目目录的新 PowerShell 终端运行：

```powershell
.\.venv\Scripts\python.exe -m scripts.check_deepseek
```

提示 `Paste DeepSeek API key (hidden)` 后粘贴 DeepSeek 密钥并回车。隐藏输入不显示字符，也不写入文件；不要发到聊天。如果已经设置 `DEEPSEEK_API_KEY`，脚本会优先使用它，绝不读取 `GEMINI_API_KEY`。

成功显示 `SUCCESS: DeepSeek returned a complete text response.` 开头的行。连通性只要求正常结束并返回非空文本，不要求恰好等于 `OK`；原文仍不显示。`USAGE` 是服务商返回的用量，`prompt_tokens` 为输入、`completion_tokens` 为输出、`total_tokens` 为总计。Token 是模型计量文本的小单位。用量缺失不代表免费，请以平台账单为准。

如果显示 `RESPONSE_UNEXPECTED`，一并反馈 `DIAGNOSTIC` 和 `USAGE` 行。`finish_reason=length` 表示生成因长度限制停止；`content_chars` 是正文字符数，`reasoning_present` 表示是否返回了思考内容，均不显示原文。脚本不会自动提高输出上限或重试。当前检查不是模型遵循指令能力的评测。

节省设置：只调用一次 `deepseek-v4-flash`；只发 `Reply only OK.`；显式关闭思考模式；输出上限 16 tokens；不自动重试、不轮询、不发送历史或材料正文。16 仅是输出上限，不含输入。自动化测试使用伪造密钥及模拟响应，不调用付费接口。

若失败，只分享 `FAILED` 和 `DIAGNOSTIC` 行，不分享密钥。401 检查密钥；402 检查余额；429 检查频率/额度，不要连续重试。

无需安装新依赖，不改 `/chat`、数据库、加密密钥或 Gemini 配置。脚本暂复用 `check_gemini.py` 中的隐藏输入及 HTTPS 辅助函数，导入不会调用 Gemini；唯一实际请求目标固定为 DeepSeek 官方地址。

保持系统/环境的代理配置，不自行改变 Clash。新终端不会继承之前仅在旧终端设置的 `HTTPS_PROXY`；如遇网络问题再单独诊断，不关闭证书校验。

依据：[首次调用](https://api-docs.deepseek.com/zh-cn/)、[思考开关](https://api-docs.deepseek.com/guides/thinking_mode/)、[价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)。本步只验证连通性，不证明真实模型的工具调用或安全防御已完成。
