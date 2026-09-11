# 材料权限演示：先用 Alice 跑通一次

这一步验证后端能否阻止越权访问，也就是读取不属于自己权限范围的材料。目前已有加密的虚构正文、[模拟助手](agent-demo.md) 和可选的 [DeepSeek 助手](deepseek-agent-demo.md)。材料访问自动记录审计日志，查看方式见 [审计日志演示](audit-demo.md)。首次使用需按 [正文加密演示](encryption-demo.md) 初始化正文。

## 准备服务

在 `D:\ai-secure` 的 PowerShell 终端执行：

```powershell
.\.venv\Scripts\python.exe -m app.database.seed_applications
```

记下它打印的材料编号。在全新的演示材料表中通常是 Alice=1、Bob=2、Carol=3。材料编号和用户编号是不同概念，即使现在恰好相同，也不能当成同一个值。

如果提示某个账户不存在，先运行 `python -m app.database.seed`（同样使用 `.venv` 中的 Python）。如果账户角色不符，不要通过重置数据库解决，先确认已有账户变更。

如果旧服务在运行，先在它所在终端按 `Ctrl+C`，然后重新启动：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

刷新 <http://127.0.0.1:8000/docs>。页面应显示版本 `0.7.0` 和“材料权限演示”接口组。如果没有，通常是仍在运行旧服务或页面没有刷新。

## 用 Alice 看见允许和拒绝

1. 展开 `POST /auth/login` → `Try it out`，将 `x-csrf-protection` 填为 `1`，正文填写下面的 JSON，再点击 `Execute`。服务器返回 200 才表示登录成功。

   ```json
   {
     "username": "alice",
     "password": "Alice-demo-2026!"
   }
   ```

2. 展开 `GET /applications` → `Try it out` → `Execute`。不需要输入用户名、角色或其他参数。结果应是 200、`decision: ALLOW`，`data` 列表只含 Alice 的材料。

3. 展开 `GET /applications/{application_id}` → `Try it out`，在 `application_id` 填 Alice 的材料编号，再执行。应返回 200 和 `ALLOW`。

   ```json
   {
     "decision": "ALLOW",
     "reason_code": "AUTHORIZED",
     "data": {
       "id": 1,
       "title": "Alice - Demo Application",
       "personal_statement": "虚构演示：我是 Alice，希望申请计算机安全方向研究生，研究兴趣是 AI Agent 的访问控制。"
     }
   }
   ```

4. 保持 Alice 登录，把同一接口的 `application_id` 改为 Bob 的材料编号，再执行。应返回 **403**，正文如下：

   ```json
   {
     "decision": "DENY",
     "reason_code": "APPLICATION_NOT_FOUND_OR_FORBIDDEN",
     "data": null
   }
   ```

这里的 403 是网关按预期拦截，不是服务坏了。`data: null` 表示没有返回材料数据；拒绝结果也不会透露标题。

`decision` 是允许或拒绝的判断，`reason_code` 是给程序识别的原因代号，`data` 是允许访问后返回的数据。材料不存在时也返回相同的拒绝结果，避免通过不同错误猜出别人的材料是否存在。

只看点击 Execute 后的 **Server response → Code / Response body**；文档下方预先列出的 403、422 是可能的结果说明，不代表实际请求失败。

## 理解 Alice 为什么被拒绝

```text
浏览器携带登录 Cookie → 后端识别 Alice → 数据库确认 Alice 是 student
请求 Bob 的材料编号 → 网关要求材料 owner_id 等于 Alice 的用户编号
Bob 的材料不符合条件 → DENY，不返回编号和标题
```

Cookie 是浏览器自动携带的登录标识。`owner_id` 是材料所属用户的编号。网关使用服务器确认的身份，不接受请求自称“我是管理员”。列表也有相同的归属条件，所以 Alice 不能先从列表看到 Bob 的标题。

## 再验证导师和管理员

先退出 Alice：`POST /auth/logout`，`x-csrf-protection` 填 `1`。然后重新登录 `lee`，密码为 `Lee-demo-2026!`，重复上述材料接口操作。

| 登录账户 | 列表应包含 | 单份访问应被拒绝 |
|---|---|---|
| alice | Alice | Bob、Carol |
| bob | Bob | Alice、Carol |
| carol | Carol | Alice、Bob |
| lee | Alice、Bob | Carol |
| admin | Alice、Bob、Carol | 不存在的材料 |

管理员密码为 `Admin-demo-2026!`。Lee 的权限来自数据库中的分配关系，不是因为所有导师都能读取所有学生。

退出后再访问任意材料接口应返回 **401**，表示没有有效登录身份。这与“已登录但没有材料访问权限”的 403 不同。

## 当前应该理解的代码

先看 `app/gateway/policies.py`：学生按归属匹配，导师按分配匹配，管理员允许全部，未知角色拒绝。

再看 `app/gateway/service.py`：读取可信身份 → 检查工具名称 → 校验参数 → 用权限条件查询 → 返回允许或拒绝。`current_user_id` 是后端传入的身份上下文，不属于 AI 或浏览器可以指定的工具参数。

目前无需接入真实模型就可以验证这些规则。模拟助手提出读取 Bob 材料的请求时，也经过同一入口。正文已在授权后解密，真实模型的恶意提示实验尚未实现，不应把这一阶段的结果当作完整安全结论。
