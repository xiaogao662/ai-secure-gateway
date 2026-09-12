# AI Secure Gateway

[简体中文](README.md) | [English](README.en.md)

面向 AI 工具调用的数据访问控制系统。以虚构申请材料为场景，将模型生成的调用提议与后端授权分离：**AI 可以提议，权限由网关决定。**

接入 DeepSeek 理解自然语言并提出工具调用，由后端根据真实登录身份独立授权，完成加密数据读取与审计。

## 演示

- **正常读取**：学生访问自己的材料，网关返回 ALLOW 和正文。
- **跨用户读取**：实际工具提议指向无权访问的材料时，网关返回 DENY，不交付正文。
- **关联审计**：管理员用请求编号核对身份、目标、决定和执行结果。

网页支持中英文切换；材料正文、原始工具参数和原因码保持原样。切换语言不发起模型请求。

## 架构

![材料读取主流程](docs/architecture.svg)

身份来自服务器端登录会话，不接受消息或工具参数中的角色声明。工具经校验和授权后才读取正文密文、解密；审计写入成功后交付结果。网关是后端模块，不是独立隔离服务。[详细数据流与异常分支](docs/architecture.md)。

## 核心能力

| 能力 | 实现 |
| --- | --- |
| 身份认证 | 服务器端随机会话；Argon2id 单向校验密码，不存明文密码 |
| 独立授权 | 学生访问本人材料，导师访问已分配学生，管理员访问全部材料 |
| 工具约束 | 仅允许两个只读工具，严格校验参数，身份由后端绑定 |
| 正文加密 | AES-256-GCM 提供保密和篡改检测；授权后解密，不是整库加密 |
| 最小审计 | 记录身份、工具、目标、决定与执行结果，不记录凭证、原始消息或正文 |
| 执行保护 | 模型返回后复验原会话；登录与模型请求限流；审计失败不交付工具数据 |

**DeepSeek 模式**使用真实模型生成工具提议；另提供可选的 Mock 模式，用固定规则验证流程，无需 API 密钥。Mock 不是本地 AI，两种模式共用真实的认证、授权、加密和审计后端。

## 安全验证

- 已记录两次 DeepSeek 跨用户读取提议被网关拒绝的样例，并核对关联审计；其中一次请求包含冒充管理员的指令。
- 自动化测试覆盖恶意工具参数、密文篡改、审计故障、会话撤销与过期、模型输出校验及限流。
- 曾复现“等待模型期间会话失效，仍继续交付正文”的问题，已增加执行前会话复验及回归测试。
- 2026-09-12 完整本地 pytest 运行：**329 项通过**，两个依赖弃用警告；不是在线持续测试状态。

模型拒绝、选错工具或处理失败，不等于网关拦截了目标读取；有限样例也不证明可防御所有提示注入。[验证证据](docs/security-validation.md) · [安全检查与修复](docs/security-review.md)

## 快速开始

需要 Python 3.12。首次在项目根目录的 Windows PowerShell 中执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m app.database.seed
.\.venv\Scripts\python.exe -m app.database.seed_applications
.\.venv\Scripts\python.exe -m app.database.seed_content
```

启动 **DeepSeek 真实模型模式**：

```powershell
.\.venv\Scripts\python.exe -m scripts.run_deepseek
```

按终端提示隐藏输入 API 密钥；若已配置 `DEEPSEEK_API_KEY` 环境变量则优先使用它。调用可能产生费用，不自动重试。不要把密钥写入网页、源码或提交到 GitHub。[连接与密钥配置](docs/deepseek-setup.md)

看到 `Application startup complete.` 后打开 [本机演示](http://127.0.0.1:8000/)，确认页面显示 DeepSeek。保持终端开启；Ctrl+C 停止服务。已有环境只需执行对应模式的启动命令。

虚构演示凭证：`alice / Alice-demo-2026!`；管理员 `admin / Admin-demo-2026!`。初始化生成的密钥与数据库不得上传或随意删除。

如暂不使用 API，可改用下面的命令启动 **Mock 固定规则模式**（不调用外部模型）。切换模式前先停止原服务：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

[完整运行与排错说明](docs/local-guide.md)

## 技术与文档

Python · FastAPI（接口）· Uvicorn（服务运行）· SQLite / SQLAlchemy（数据存储与访问）· cryptography（加密）· argon2-cffi（密码校验）· 原生 HTML/CSS/JavaScript · pytest / Playwright（自动化检查）。

| 文档 | 内容 |
| --- | --- |
| [运行与技术说明](docs/local-guide.md) | 初始化、接口操作、测试命令和模块说明 |
| [系统架构](docs/architecture.md) | 数据流与信任边界 |
| [威胁模型](docs/threat-model.md) | 攻击者能力、可信前提与未覆盖风险 |
| [网页操作](docs/web-demo.md) | 演示流程及结果解读 |
| [正文加密](docs/encryption-demo.md) | 密钥、记录绑定与故障验证 |
| [安全验证](docs/security-validation.md) | 实验记录与证据边界 |

## 适用范围

仅使用虚构数据进行本机演示，不是通用聊天产品。默认 HTTP 配置和公开演示密码不适合直接部署到公网。当前不覆盖主机或密钥失窃、恶意管理员、防篡改日志、跨进程限流及所有并发撤销情形。

模型不接收服务器会话、加密密钥或工具返回的正文；用户主动写入消息的内容仍可能发送给模型供应商。参考 OWASP 风险指导不代表获得安全认证。
