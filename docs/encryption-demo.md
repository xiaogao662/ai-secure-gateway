# 正文加密：有权限才能解密，密文被改动也不能正常读取

这一阶段仍然使用之前的两个材料接口。变化是单份读取增加 `personal_statement` 正文字段，而数据库只保存这段正文的密文。

## 先准备一次

在 `D:\ai-secure` 执行（首次部署需先按 README 准备用户和材料）：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m app.database.seed_content
```

首次新增三份加密正文，再次运行通常显示新增 0 份。已有正文、密钥、账户和日志不会被重置。如果本次工作中已由助手初始化，不需要再运行。

默认密钥位于 `.secrets/application.key`，数据库位于 `data/ai_secure.db`。密钥是解密所必需的秘密，不要上传或删除它；程序不会把密钥打印出来。已有密文但密钥丢失时，程序拒绝自动生成新密钥，因为新密钥无法解开旧数据。

停止旧服务（其终端按 `Ctrl+C`），再启动以加载密钥：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

刷新 <http://127.0.0.1:8000/docs>，当前应显示版本 `0.7.0`。

## 亲手看结果

1. 用 `POST /auth/login` 登录 Alice，`x-csrf-protection` 填 `1`，正文如下：

   ```json
   {"username": "alice", "password": "Alice-demo-2026!"}
   ```

2. 执行 `GET /applications`，仍只会看到自己的编号和标题，列表不会读取或解密任何正文。
3. 执行 `GET /applications/{application_id}`，填 Alice 的材料编号（默认 `1`）。返回 200、`ALLOW`，并多出正文：

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

4. 把编号改为 Bob 的材料编号（默认 `2`），仍应得到 403、`DENY`、`data: null`。这次测试已进一步验证：拒绝请求不会触发正文解密，也不会先查询 Bob 的正文密文。

编号以本地实际初始化结果为准。浏览器能看到自己的明文是预期功能：数据库保存密文，权限通过后后端才解密并把正文返回给获准用户。

## 密码哈希与正文加密的区别

| 数据 | 保存方式 | 原因 |
|---|---|---|
| 登录密码 | Argon2id 哈希 | 只需核对密码，不需要还原密码 |
| 材料正文 | AES-256-GCM 密文 | 获准用户需要读取原文，所以必须能解密 |

AES-GCM 同时保护内容的保密性和完整性，使用成熟的 `cryptography` 库。AES-256 中的 256 是密钥位数，对应 32 字节。

加密时还用到两个概念：nonce 是每次加密使用的新值，在同一密钥下不能重复；AAD 是不加密但参加完整性校验的信息。这里 nonce 为 12 字节随机值，AAD 包含字段版本、材料编号和所属用户编号，防止把另一份材料的密文搬到这条记录后仍成功解密。

`application_contents` 表只有材料编号、nonce、ciphertext 三列。Ciphertext 就是密文，其中已包含库生成的认证标签；标签用于检测篡改。数据库里仍然有明文用户名、标题、归属和日志，保护范围是正文，不是整个数据库。

## 篡改和失败如何验证

不要手动破坏本机数据库。运行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_encryption.py
```

测试在临时数据库中修改密文、nonce、密钥或绑定信息，验证解密失败；还监测数据库查询和解密调用，证明列表、未登录和越权请求不会接触正文密文或解密函数。

如果获准用户读取时发生加密相关问题，接口统一返回 503：

```json
{"detail": "Application content unavailable"}
```

管理员可在审计日志中区分原因：

| reason_code | 含义 |
|---|---|
| ENCRYPTION_NOT_CONFIGURED | 服务没有加载密钥，需确认配置并重启 |
| CONTENT_NOT_INITIALIZED | 该材料尚未初始化正文 |
| DECRYPTION_FAILED | 密文被改动，或密钥、nonce、绑定信息不匹配 |

这些情况记录 `decision=ALLOW`、`execution_status=ERROR`：有读取权限，但没有成功拿到正文。无权访问 Bob 的 Alice 仍然只得到 403，不会得知这些内部状态。日志不会保存解密后的正文、密钥或完整异常。

## 当前的实际边界

密钥默认是同机本地文件，只与数据库分开存放，不是独立的密钥管理服务；文件权限沿用 Windows 目录权限。也支持 `AI_SECURE_DATA_KEY` 环境变量，格式为 32 字节密钥的标准 Base64 文本，优先于文件。Base64 只是文本编码，并不保护密钥。不要随意更换密钥，当前没有密钥轮换和恢复界面。

本项目的初始化正文是公开虚构示例，所以源码中包含示例原文。真实材料不应硬编码进源码。加密不能代替权限检查，不能保护已被授权返回的明文，也不能抵御同时获得服务器和密钥的攻击者。AAD 绑定不提供旧合法密文的回放检测。

推荐先读 `app/crypto/field_encryption.py`，理解 encrypt/decrypt 使用同一份绑定信息；再读 `app/gateway/service.py` 中权限检查、密文查询、解密、审计的先后顺序。
