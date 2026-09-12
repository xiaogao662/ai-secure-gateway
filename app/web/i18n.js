"use strict";
// Only interface strings are translated. No network, storage, or HTML insertion.
window.gatewayI18n = (() => {
  let language = "zh";
  const dictionary = {
  "AI Secure Gateway · 安全演示台": "AI Secure Gateway · Security Console",
  "AI Secure Gateway 首页": "AI Secure Gateway home",
  "本机安全实验室": "Local security lab",
  "接口文档 ↗": "API docs ↗",
  "AI 可以提议，": "AI proposes. ",
  "权限由网关决定。": "The gateway decides.",
  "身份、意图、授权。每一次访问，都有据可查。": "Identity, intent, authorization. Evidence for every request.",
  "当前模式": "ACTIVE MODE",
  "正在确认…": "Checking…",
  "加载配置不会调用模型": "Loading settings does not call the model",
  "当前身份": "Current identity",
  "未登录": "Signed out",
  "身份以服务器端会话为准": "Identity comes from the server session",
  "使用虚构演示账户进入工作台。": "Sign in with a fictional demo account.",
  "用户名": "Username",
  "密码": "Password",
  "例如 alice": "e.g. alice",
  "现有演示账户密码": "Your demo account password",
  "登录工作台": "Sign in",
  "确认切换账户": "Confirm switch",
  "取消切换": "Cancel switch",
  "切换账户": "Switch account",
  "退出": "Sign out",
  "切换成功前，当前身份保持不变。": "Your identity stays unchanged until the switch succeeds.",
  "演示账户": "Demo accounts",
  "alice、bob、carol：学生": "alice, bob, carol: students",
  "lee：导师 · admin：管理员": "lee: advisor · admin: administrator",
  "请使用已有账户密码。": "Use your existing demo password.",
  "模型 API 密钥只在启动终端输入。": "Enter model API keys only in the launch terminal.",
  "安全边界": "TRUST BOUNDARY",
  "消息中的“我是管理员”": "Saying “I am an administrator”",
  "不会改变这里的登录身份。": "does not change your login identity.",
  "访问请求": "Access request",
  "单次调用": "Single call",
  "仅支持材料查询，不提供通用聊天。访问权限由网关判断。": "Application queries only, not general chat. The gateway checks access.",
  "示例请求，仅填入不发送": "Example requests: fill only, never auto-send",
  "列出材料": "List applications",
  "读取材料 1": "Read application 1",
  "读取材料 2": "Read application 2",
  "身份伪造尝试": "Impersonation attempt",
  "例如：列出我能访问的材料，或读取材料 2": "e.g. List my applications, or Read application 2",
  "/ 1000 · 示例按钮只填入文字": "/ 1000 · Examples fill the input only",
  "发送请求 →": "Send request →",
  "处理中…": "Processing…",
  "真实模型模式下，无关问题也可能消耗额度；不自动重试，请勿输入真实敏感信息。": "Real-model requests may incur charges, even for unrelated questions. No automatic retries. Do not enter real sensitive data.",
  "正在确认登录状态…": "Checking session…",
  "最近一次请求结果": "Most recent request result",
  "查看执行证据": "Execution evidence",
  "尚未发送": "No request yet",
  "登录身份": "Login identity",
  "AI 工具提议": "AI tool proposal",
  "GATEWAY DECISION · 网关决定": "GATEWAY DECISION",
  "待验证": "Pending",
  "发送后请核对实际工具名称和目标编号。": "After sending, check the actual tool and target ID.",
  "允许或拒绝由网关返回，页面不决定权限。": "The gateway returns the decision; this page does not authorize access.",
  "TOOL PROPOSAL · 不代表授权": "TOOL PROPOSAL · NOT AUTHORIZATION",
  "等待工具提议": "Awaiting a tool proposal",
  "查看原始工具参数": "View raw tool arguments",
  "交付结果": "Delivered result",
  "仅显示最近一次结果": "Most recent result only",
  "发送请求后，在这里查看材料列表、正文或拒绝说明。": "Send a request to see permitted records, content, or a denial.",
  "请求编号": "Request ID",
  "复制编号": "Copy ID",
  "模型用量：—": "Model usage: —",
  "审计日志": "Audit log",
  "仅管理员 · 不调用模型": "Admin only · No model calls",
  "本页请求编号筛选": "Filter loaded request IDs",
  "粘贴 request_id": "Paste request_id",
  "查看最新 20 条": "Load latest 20",
  "点击后加载；筛选仅针对最新 20 条，不搜索全部历史。": "Load on demand. Filtering applies only to the latest 20 events, not the full history.",
  "时间 / 请求编号": "Time / Request ID",
  "身份": "Identity",
  "工具 / 目标": "Tool / Target",
  "决定 / 执行": "Decision / Execution",
  "原因": "Reason",
  "仅验证具体样例，不宣称防御所有提示注入。": "Specific cases only; not a claim to prevent all prompt injection.",
  "等待已停止；服务器可能仍在处理，已有用量不会撤销。请勿立即重复发送。": "Waiting stopped; the server may still be processing. Usage is not reversed. Do not resend immediately.",
  "无法取得有效响应。请确认本机服务仍运行；请求不会自动重试。": "No valid response. Check that the local server is running. Requests are not retried automatically.",
  "暂时无法确认登录身份，请稍后再试。": "Unable to verify the session. Please try again later.",
  "已复制请求编号，可切换管理员后粘贴到日志筛选框；仅筛选已加载的最新 20 条。": "Request ID copied. Sign in as admin and paste it into the log filter; only the latest 20 loaded events are filtered.",
  "自动复制不可用，请选中上方请求编号手动复制。": "Clipboard access unavailable. Select the request ID above to copy it manually.",
  "正在验证登录身份…": "Verifying credentials…",
  "登录成功。示例只填入文字，点击发送才会发出请求。": "Signed in. Examples fill the input; only Send submits a request.",
  "用户名或密码不正确；未切换账户。": "Incorrect username or password; the account was not switched.",
  "登录失败，请检查输入和服务状态。": "Sign-in failed. Check your input and the server status.",
  "退出未确认，请重试退出操作。": "Sign-out was not confirmed. Please try signing out again.",
  "已退出，页面中的上次结果已清除。": "Signed out. Previous results have been cleared.",
  "本地模拟：不消耗模型 tokens": "Local simulation: no model tokens used",
  "模型用量：未提供（不代表免费）": "Model usage: not reported (not necessarily free)",
  "正在确认身份并处理请求，请勿重复发送…": "Checking identity and processing your request. Please do not resend…",
  "请先登录。": "Please sign in first.",
  "会话已失效，请重新登录。": "Session expired or revoked. Please sign in again.",
  "请求限流": "Rate limited",
  "这是调用频率限制，不是目标材料的权限决定。": "This is a request-frequency limit, not an authorization decision for the target record.",
  "发送过于频繁，本次未调用模型，也未执行工具。": "Too many requests. No model or tool was called for this attempt.",
  "本次限流拒绝：未调用模型": "Rate limited: no model call",
  "没有可展示的工具提议": "No tool proposal to display",
  "列出可访问的材料": "List accessible applications",
  "其他工具提议 · 请展开核对": "Other tool proposal · expand to inspect",
  "本次没有工具提议": "No tool proposed",
  "允许列出当前账户可见的材料，不代表获准读取所有正文。": "Only lists records visible to this account; it does not authorize reading every body.",
  "仅允许本次工具和目标；其他材料仍需单独检查权限。": "Only this tool and target are authorized. Other records require separate checks.",
  "目标不存在或当前账户无权访问，系统不区分这两种情况，也不交付正文。": "The target does not exist or this account cannot access it. These cases are not distinguished; no body is delivered.",
  "工具参数不符合要求，调用被拒绝；不能把它当成资源权限规则已通过验证。": "Invalid tool arguments. The call was rejected; this does not demonstrate resource-level authorization enforcement.",
  "工具不在允许清单中，调用被拒绝。": "The tool is not allowlisted. The call was rejected.",
  "登录身份无效，调用被拒绝。": "The session is invalid. The call was rejected.",
  "请结合实际工具、目标和原始原因码解读本次决定。": "Interpret this decision with the actual tool, target, and raw reason code.",
  "未提供回答": "No answer provided",
  "网关拒绝了这次调用，没有返回材料正文。请检查目标编号及当前账户权限。": "The gateway denied this call and returned no record body. Check the target ID and account permissions.",
  "网关拒绝：未交付目标材料。请结合实际工具和目标编号解读。": "Gateway denied: no target record delivered. Check the actual tool and target ID.",
  "网关允许了上述工具调用；不代表允许访问所有材料。": "The gateway authorized this tool call, not access to all records.",
  "处理失败": "Processing failed",
  "无授权决定": "No decision",
  "未获得网关结果": "No gateway result",
  "没有可展示的网关决定，不能作为越权被网关拒绝的证据。": "No gateway decision is available. This is not evidence of an unauthorized read being denied.",
  "没有工具调用，不计作网关拦截越权读取。": "No tool call occurred; this is not a gateway denial of an unauthorized read.",
  "没有可交付的结果。": "No result to deliver.",
  "本次没有提出工具调用。请明确要列出材料，还是读取某个材料编号；每次只读取一份。": "No tool call was proposed. Specify whether to list applications or read one application ID at a time.",
  "这不是网关权限拒绝的证据。记录错误码，先不要连续重试。": "This is not evidence of gateway authorization denial. Note the error code and avoid repeated retries.",
  "本次没有工具调用，不算网关拦截了越权读取。": "No tool was called. This does not count as a gateway denial of an unauthorized read.",
  "审计日志仅允许管理员查看。": "Only administrators can view audit logs.",
  "无法读取日志，请确认当前仍是管理员。": "Unable to read audit logs. Confirm that the current account is still an administrator.",
  "日志已加载，没有调用模型。": "Logs loaded without calling the model.",
  "其他页面切换了会话，旧结果已清除。": "Another page changed the session. Previous results were cleared.",
  "已重新确认登录状态，旧结果已清除。": "Session rechecked. Previous results were cleared.",
  "DeepSeek · 真实模型": "DeepSeek · Real model",
  "Mock · 固定规则": "Mock · Fixed rules",
  "每用户 60 秒 ≤5 次 · 每次启动 ≤20 次尝试 · 输出 ≤128 tokens": "≤5 attempts/user/60s · ≤20 attempts/start · ≤128 output tokens",
  "本地模拟 · 不消耗模型 tokens": "Local simulation · No model tokens",
  "点击发送后，消息可能发送给 DeepSeek；无关问题也可能消耗额度。不自动重试，请勿输入真实敏感信息。": "Send may transmit your message to DeepSeek. Even unrelated requests may incur charges. No automatic retries; do not enter real sensitive data.",
  "当前为固定规则模拟，无外部模型调用，不消耗模型额度。": "Fixed-rule simulation: no external model calls or model charges.",
  "已恢复登录身份。点击示例不会自动发送。": "Session restored. Examples do not send automatically.",
  "请先登录，再发送访问请求。": "Sign in before sending an access request.",
  "材料": "Application",
  "未知": "Unknown",
  "正文与工具返回内容保持原文。": "Record bodies and tool-returned content remain in their original language."
};
  const values = new Map();
  const roles = {"学生":"Student", "导师":"Advisor", "管理员":"Administrator"};
  function translate(source, id = "") {
    const value = String(source ?? "");
    if (language !== "en") return value;
    if (Object.hasOwn(dictionary, value)) return dictionary[value];
    if (id === "role") {
      const match = value.match(/^(学生|导师|管理员) · 用户 ([0-9]+)$/);
      if (match) return `${roles[match[1]]} · User ${match[2]}`;
    }
    if (id === "result-actor") {
      const match = value.match(/^([\s\S]*) · (学生|导师|管理员)$/);
      if (match) return `${match[1]} · ${roles[match[2]]}`;
    }
    const patterns = [
      [/^读取材料 · ([0-9]+|编号待核对)$/, m => `Read application · ${m[1] === "编号待核对" ? "check ID" : m[1]}`],
      [/^Tokens 输入 ([0-9—]+) \/ 输出 ([0-9—]+) \/ 合计 ([0-9—]+)$/, m => `Tokens in ${m[1]} / out ${m[2]} / total ${m[3]}`],
      [/^显示 ([0-9]+) \/ ([0-9]+) 条。时间采用日志原始 UTC 时区；编号筛选仅针对本页。$/, m => `Showing ${m[1]} / ${m[2]} events. Original UTC timestamps; filter applies to this page only.`],
      [/^登录尝试过于频繁，请至少等待 ([0-9]+) 秒再手动尝试。本次未校验密码，也未切换账户。$/, m => `Too many sign-in attempts. Wait at least ${m[1]} seconds. Password was not checked; account unchanged.`],
      [/^请至少等待 ([0-9]+) 秒后再手动发送；页面不会自动重试。这不是材料权限拒绝。$/, m => `Wait at least ${m[1]} seconds before sending again. No automatic retry. This is not a record authorization denial.`],
    ];
    for (const [pattern, format] of patterns) { const match = value.match(pattern); if (match) return format(match); }
    return value;
  }
  function text(id, value, local = true) {
    const source = String(value ?? "");
    values.set(id, {source, local});
    document.getElementById(id).textContent = local ? translate(source, id) : source;
  }
  // Capture static text nodes once; never scan server results or user input.
  const staticNodes = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const node = walker.currentNode;
    if (node.parentElement.closest("script, pre, #identity, #role, #reason, #audit-rows, #result-actor, #language-toggle")) continue;
    const key = node.textContent.trim();
    if (Object.hasOwn(dictionary, key)) staticNodes.push({node, source:node.textContent, key});
  }
  const attributes = [];
  document.querySelectorAll("[placeholder], [aria-label]").forEach(element => {
    for (const name of ["placeholder", "aria-label"]) {
      const source = element.getAttribute(name);
      if (source && Object.hasOwn(dictionary, source)) attributes.push({element, name, source});
    }
  });
  function render() {
    document.documentElement.lang = language === "en" ? "en" : "zh-CN";
    document.title = translate("AI Secure Gateway · 安全演示台");
    for (const item of staticNodes) {
      if (item.node.isConnected) item.node.textContent = language === "en" ? item.source.replace(item.key, dictionary[item.key]) : item.source;
    }
    for (const item of attributes) item.element.setAttribute(item.name, translate(item.source));
    for (const [id, item] of values) document.getElementById(id).textContent = item.local ? translate(item.source, id) : item.source;
    const button = document.getElementById("language-toggle");
    button.textContent = language === "en" ? "中文" : "English";
    button.setAttribute("aria-label", language === "en" ? "切换到中文" : "Switch to English");
  }
  document.getElementById("language-toggle").addEventListener("click", () => {
    language = language === "en" ? "zh" : "en";
    render();
    document.dispatchEvent(new Event("gateway-language-change"));
  });
  return {text, translate, get language() {return language;}};
})();
