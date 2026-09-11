# 审计日志演示：把允许和拒绝变成可查看的记录

权限网关负责拦截不允许的访问，审计日志负责事后还原发生了什么。这一步不需要理解所有代码，先观察一次允许和一次拒绝。

## 1. 重启并刷新

在旧服务所在终端按 `Ctrl+C`，然后在 `D:\ai-secure` 执行：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

刷新 <http://127.0.0.1:8000/docs>。确认页面版本是 `0.7.0`，并出现“审计日志”接口组。重启会自动添加缺少的表，不会删除旧数据。首次升级到正文阶段需要先完成 [加密正文初始化](encryption-demo.md)，不要重建数据库。

## 2. 用 Alice 生成两次访问

执行 `POST /auth/login`：点击 `Try it out`，将 `x-csrf-protection` 填为 `1`，正文填入：

```json
{"username": "alice", "password": "Alice-demo-2026!"}
```

确认实际返回 200，然后执行 `GET /applications/{application_id}` 两次：

| application_id | 默认演示材料 | 应看到的结果 |
|---|---|---|
| 1 | Alice 的材料 | 200、ALLOW |
| 2 | Bob 的材料 | 403、DENY |

材料编号以初始化命令打印的实际值为准。两个材料 GET 接口不用填写 `x-csrf-protection`。403 表示网关正常拒绝访问。

现在每次访问已经各写入一条日志。可以在 **Server response → Response headers** 找到 `x-request-id`：这是服务器给本次请求的编号，稍后能在日志中找到同一个编号。它不是密码，也不需要手动输入。

## 3. 确认 Alice 无权查看完整日志

保持 Alice 登录，展开 `GET /audit/logs` → `Try it out`，保留 `limit=20`、`offset=0`，点击 `Execute`。应返回 **403**：

```json
{"detail": "Admin access required"}
```

日志包含不同用户的访问情况，所以只允许管理员查看。这里的拒绝与 Alice 不能读 Bob 材料一样，都是预期的权限控制。

## 4. 换管理员查看

先执行 `POST /auth/logout`，`x-csrf-protection` 填 `1`。再执行 `POST /auth/login`，同样填请求头 `1`，正文改为：

```json
{"username": "admin", "password": "Admin-demo-2026!"}
```

登录成功后，再执行 `GET /audit/logs`，保留默认参数。应返回 **200** 和日志列表，最新记录在最上方。找到 Alice 的两条记录，重点比较：

| 字段 | Alice 读自己 | Alice 读 Bob |
|---|---|---|
| user_id | Alice 的用户编号 | Alice 的用户编号 |
| role | student | student |
| tool_name | read_application | read_application |
| application_id | 1 | 2 |
| decision | ALLOW | DENY |
| reason_code | AUTHORIZED | APPLICATION_NOT_FOUND_OR_FORBIDDEN |
| execution_status | SUCCESS | NOT_EXECUTED |

`decision` 是请求允许/拒绝结果；`execution_status` 是执行结果。`timestamp` 是 UTC 时间，北京时间需要加 8 小时。`request_id` 可与刚才接口响应头中的编号对应。列表里可能还有自动验证或此前手动操作产生的记录，这些记录会被保留。

`limit` 表示最多返回多少条（上限 100），`offset` 表示跳过多少条最新记录。先用默认值即可。查看日志本身不会新增一条材料访问日志。

## 这一阶段需要理解什么

当前材料调用链是：

```text
确认身份 → 网关判断 → 授权后查询及解密 → 保存处理日志 → 返回结果
```

如果日志写不进去，接口返回 503，不返回材料数据；这是当前项目选择的失败处理方式。未登录或参数错误导致请求在进入网关前被拒绝，也会记录。日志里不会保存密码、会话标识、材料标题、正文或原始攻击文本。

先看 `app/audit/service.py` 中 `record_event` 的字段，再看 `app/gateway/service.py` 中“写入日志后再返回”的顺序。暂时不用展开理解补记早期拒绝的 HTTP 代码。

日志能帮助追踪，不能代替权限检查。当前日志是普通 SQLite 记录，没有防篡改签名或独立备份，也没有审计全部登录、日志查看和任意 URL 请求；不能把它描述成不可篡改或覆盖所有系统事件的日志系统。
