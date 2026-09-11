# Gemini：先做一次最小连接测试

本步只确认本机程序能否用你的 API 密钥调用 Gemini，不把真实模型接入 `/chat`。API 密钥是调用服务的凭证，不能代替项目登录身份，也不是加密材料的密钥。

## 在本机运行

在一个新的 PowerShell 终端中执行（不用停止现有 Web 服务）：

```powershell
cd D:\ai-secure
.\.venv\Scripts\python.exe -m scripts.check_gemini
```

看到 `Paste Gemini API key (hidden), then press Enter:` 后，粘贴自己的 Gemini 密钥并按回车。输入时不显示字符或星号是正常现象。必须在支持隐藏输入的交互终端运行，不能把密钥当作命令参数。不要把密钥粘贴到聊天、源码或 `/docs`。

脚本不会把输入的密钥写入文件；运行结束后也不会为下次调用保存它。如果你此前已自行设置 `GEMINI_API_KEY`，脚本会优先使用它，不再提示输入。环境变量就是进程读取配置的一种方式；这一步不要求设置它，也不读取 `.env` 或材料密钥文件。

成功会显示：

```text
SUCCESS: Gemini replied OK. No application data was sent.
```

把成功行或 `FAILED:` 行告诉我即可，不要分享密钥或包含密钥的截图。下一步才会把 Gemini 的工具提议接到已有网关。

## 这条命令做了什么

- 使用官方列出的 `gemini-2.5-flash` 和 `generateContent` 接口。本步只做文字连通性检查，后续工具接入时再确认模型选择与支持。
- 只发送 `Reply with exactly OK and nothing else.`，意思是“只回复 OK”。不读取数据库、申请材料、登录 Cookie 或加密密钥，不生成材料访问审计日志。
- 只发起一次请求，不自动重试；关闭此模型的思考预算，输出上限为 64 tokens。Token 是模型计算文本长度和用量的小单位；上限用于限制生成量，不等于固定费用。
- 可能消耗免费额度；若项目已启用付费，也可能计费。以你的项目额度和 [官方价格](https://ai.google.dev/gemini-api/docs/pricing) 为准。
- 使用 Python 自带的 HTTPS 请求功能，不需要安装新库。HTTPS 是验证服务器并加密传输内容的连接方式；脚本保持证书校验，不跟随重定向，不把密钥放在网址中。
- 网络连接/读取等待设置为 20 秒；不是严格的整个程序耗时上限。使用系统/环境中的代理配置，不自行修改网络设置。
- 正常结果只显示固定成功提示；失败不打印密钥、原始响应或底层异常详情。

## 连接超时与模型 404 的诊断

本机已确认 Clash Verge 的代理端口为 `7897`，通过它进行不带密钥的 HTTPS 检查收到过服务器响应。如果在同一台电脑上遇到直连超时，可以在运行脚本的 PowerShell 中设置：

```powershell
$env:HTTPS_PROXY = "http://127.0.0.1:7897"
```

这只修改当前终端及后续子进程的配置，关闭终端后不保留，不修改系统代理。其他电脑或 Clash 设置变更后必须重新确认端口，不能照抄。浏览器能访问不代表 Python 使用相同的网络路径。

如果生成请求得到 `HTTP_404`，先查询官方 API 返回的模型列表，不直接猜另一个名称：

```powershell
.\.venv\Scripts\python.exe -m scripts.check_gemini --list-models
```

按提示隐藏输入密钥，随后会显示 `Connecting...`（正在连接）。此选项只发起一次模型元数据 GET 请求，不调用模型生成、不改变默认模型、不接数据库。GET 在这里是查询信息的请求方式。

成功显示 `MODEL_LIST_OK`、支持 `generateContent` 的 Gemini 模型名称，以及当前配置的 `gemini-2.5-flash` 是否出现在本页。`generateContent` 是当前测试使用的内容生成接口。列表接口成功并不证明每个模型都有可用额度或生成权限。

把模型名称和最后的状态行告诉助手即可。若出现 `MORE_PAGES`，本页并不完整；不能用本页没有出现某名称证明模型已下线。脚本不会自动请求后续页或尝试其他模型。如果列表请求也返回 404，需要继续检查接口响应来源和网络路径，不能归因于某个模型名称。

官方 [模型列表接口](https://ai.google.dev/api/models) 可返回模型名称与支持的方法；[模型停用时间表](https://ai.google.dev/gemini-api/docs/deprecations) 是另一项参考，具体情况仍需结合实际响应判断。

如果模型显示 `LISTED` 而之前生成返回 404，仍不能证明生成权限或额度可用。诊断脚本现在会把 HTTP 错误的安全摘要放在额外一行 `DIAGNOSTIC:` 中。再次执行不带 `--list-models` 的原命令只生成一次，将 `FAILED:` 和 `DIAGNOSTIC:` 两行一并反馈即可。

- `format` 表示响应是结构化 JSON 错误、HTML 页面或其他格式；HTML 不是代理故障的充分证据。
- `status` 仅显示固定清单中的错误状态，如 `NOT_FOUND`，未知字段统一为 `UNKNOWN`。
- `hint` 是根据错误文字匹配的固定线索，如 `MODEL_OR_METHOD_UNAVAILABLE`（模型或调用方法不可用）或 `REGION_RESTRICTION`（地区限制）。它不是最终诊断结论。
- 不打印原始错误消息、项目标识、响应头或任意错误详情，避免服务器回显输入造成泄露。原始错误体最多读取 16 KiB，读取失败仍保留已收到的 HTTP 状态。

错误排查参考 [Google 官方指南](https://ai.google.dev/gemini-api/docs/troubleshooting)。

## 看懂常见失败

| 提示 | 含义与下一步 |
| --- | --- |
| `INVALID_KEY_INPUT` | 空输入或异常字符，重新检查本机粘贴内容 |
| `INPUT_UNAVAILABLE` | 当前终端无法隐藏输入，请换交互式 PowerShell |
| `HTTP_400` | 可能涉及密钥、请求兼容性或地区，不能仅凭此码确定原因 |
| `HTTP_401` / `HTTP_403` | 检查密钥有效性、项目权限、密钥限制与地区可用性 |
| `HTTP_404` | 当前模型或接口不可用，需要核对模型，不要急着付费 |
| `HTTP_429` | 频率或额度限制；先查 AI Studio 用量，不要连续重试 |
| `NETWORK_ERROR` | 网络、域名解析、代理、证书问题或超时；不要关闭证书校验来解决 |
| `RESPONSE_INVALID` / `RESPONSE_UNEXPECTED` | 收到了成功 HTTP 响应，但没有得到完整的预期 OK；不能算本次检查通过 |
| `HTTP_5xx` | 服务端返回错误，可稍后再尝试 |

密钥创建成功不代表所在地区和该模型一定可调用；参见 [官方适用地区](https://ai.google.dev/gemini-api/docs/available-regions)。

## 验证范围

`tests/test_gemini_check.py` 使用伪造密钥和模拟响应，不访问 Google，不产生费用。它检查请求内容、重定向拒绝、错误不泄露密钥，以及成功/失败判断。这些离线测试通过，不能代替你在本机完成真实连接测试。

实现依据：[模型说明](https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash)、[生成接口](https://ai.google.dev/api/generate-content)、[官方密钥指南](https://ai.google.dev/gemini-api/docs/api-key)。
