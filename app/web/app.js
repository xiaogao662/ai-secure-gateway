"use strict";
const $ = (id) => document.getElementById(id);
let user = null, busy = false, epoch = 0, auditRows = [];
let editingAccount = false;
const controllers = new Set();
const channel = typeof BroadcastChannel === "function" ? new BroadcastChannel("ai-secure-session") : null;
const roleNames = {student: "学生", advisor: "导师", admin: "管理员"};
const requestIdPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function notice(text, tone = "") { $("notice").textContent = text; $("notice").dataset.tone = tone; }
function controls() {
  document.querySelectorAll("button, input, textarea").forEach((el) => { el.disabled = busy; });
  $("send-button").disabled = busy || !user || editingAccount;
  $("login-form").hidden = Boolean(user) && !editingAccount;
  $("switch-account").hidden = !user || editingAccount;
  $("cancel-switch").hidden = !user || !editingAccount;
  $("logout-button").hidden = !user || editingAccount;
  $("demo-accounts").hidden = Boolean(user) && !editingAccount;
  $("login-button").textContent = user ? "确认切换账户" : "登录工作台";
  $("login-hint").textContent = user ? "切换成功前，当前身份保持不变。" : "使用虚构演示账户进入工作台。";
  $("logout-button").disabled = busy || !user;
  $("copy-request-id").disabled = busy || !user || !requestIdPattern.test($("request-id").textContent);
  $("send-button").textContent = busy ? "处理中…" : "发送请求 →";
  document.querySelector("main").setAttribute("aria-busy", String(busy));
}
function clearResults() {
  $("tool-call").textContent = "等待工具提议";
  $("decision").textContent = "待验证"; $("decision").className = "badge neutral";
  $("reason").textContent = "允许或拒绝由网关返回，页面不决定权限。";
  $("decision-help").textContent = "发送后请同时核对左侧工具名称和目标编号。";
  $("copy-status").textContent = "";
  $("answer").textContent = "发送请求后，在这里查看材料列表、正文或拒绝说明。";
  $("request-id").textContent = "—"; $("usage").textContent = "模型用量：—";
  $("http-status").textContent = "尚未发送"; $("result-actor").textContent = "仅显示最近一次结果";
  auditRows = []; $("audit-rows").replaceChildren(); $("audit-filter").value = "";
  $("audit-note").textContent = "点击后加载；筛选仅针对最新 20 条，不搜索全部历史。";
}
function setUser(next) {
  if (user?.id !== next?.id || user?.role !== next?.role) { clearResults(); editingAccount = false; $("username").value = ""; $("password").value = ""; }
  user = next;
  $("identity").textContent = user ? user.username : "未登录";
  $("role").textContent = user ? `${roleNames[user.role] || user.role} · 用户 ${user.id}` : "身份以服务器端会话为准";
  $("audit-panel").hidden = user?.role !== "admin";
  controls();
}
async function request(path, body) {
  const controller = new AbortController(); controllers.add(controller);
  const timer = setTimeout(() => controller.abort(), 30000);
  try {
    const response = await fetch(path, {
      method: body === undefined ? "GET" : "POST", credentials: "same-origin", cache: "no-store",
      headers: body === undefined ? {} : {"Content-Type": "application/json", "X-CSRF-Protection": "1"},
      body: body === undefined ? undefined : JSON.stringify(body), signal: controller.signal,
    });
    const data = await response.json();
    return {code: response.status, data, id: response.headers.get("X-Request-ID")};
  } catch (error) {
    throw new Error(error.name === "AbortError"
      ? "等待已停止；服务器可能仍在处理，已有用量不会撤销。请勿立即重复发送。"
      : "无法取得有效响应。请确认本机服务仍运行；请求不会自动重试。");
  } finally { clearTimeout(timer); controllers.delete(controller); }
}
async function run(action) {
  if (busy) return;
  busy = true; controls(); const ticket = ++epoch;
  try { await action(ticket); }
  catch (error) { if (ticket === epoch) notice(error.message, "error"); }
  finally { if (ticket === epoch) { busy = false; controls(); } }
}
async function currentUser(ticket) {
  const response = await request("/auth/me");
  if (ticket !== epoch) return null;
  if (response.code === 401) { setUser(null); return null; }
  if (response.code !== 200) throw new Error("暂时无法确认登录身份，请稍后再试。");
  setUser(response.data); return response.data;
}
function invalidate() {
  ++epoch; controllers.forEach((controller) => controller.abort());
  busy = false; clearResults(); $("password").value = ""; $("message").value = ""; $("char-count").textContent = "0";
  setUser(null);
}
function signalSessionChange() { channel?.postMessage("changed"); }

$("switch-account").addEventListener("click", () => {
  if (busy || !user) return;
  editingAccount = true; $("username").value = ""; $("password").value = "";
  controls(); $("username").focus();
});
$("cancel-switch").addEventListener("click", () => {
  if (busy || !user) return;
  editingAccount = false; $("username").value = ""; $("password").value = "";
  controls(); $("switch-account").focus();
});

$("copy-request-id").addEventListener("click", () => {
  const id = $("request-id").textContent;
  if (busy || !user || !requestIdPattern.test(id)) return;
  run(async (ticket) => {
    try {
      if (!navigator.clipboard?.writeText) throw new Error("Clipboard unavailable");
      await navigator.clipboard.writeText(id);
      if (ticket === epoch) $("copy-status").textContent = "已复制请求编号，可切换管理员后粘贴到日志筛选框；仅筛选已加载的最新 20 条。";
    } catch {
      if (ticket === epoch) $("copy-status").textContent = "自动复制不可用，请选中上方请求编号手动复制。";
    }
  });
});

$("login-form").addEventListener("submit", (event) => {
  event.preventDefault();
  if (busy) return;
  const credentials = {username: $("username").value.trim(), password: $("password").value};
  $("password").value = ""; clearResults();
  run(async (ticket) => {
    notice("正在验证登录身份…");
    const response = await request("/auth/login", credentials);
    if (ticket !== epoch) return;
    if (response.code === 200) {
      editingAccount = false; $("username").value = "";
      setUser(response.data); $("message").value = ""; $("char-count").textContent = "0";
      signalSessionChange(); notice("登录成功。示例只填入文字，点击发送才会发出请求。", "ok");
    } else {
      await currentUser(ticket);
      if (ticket === epoch && response.code === 429 && response.data.reason_code === "LOGIN_RATE_LIMIT") {
        const seconds = Number.isSafeInteger(response.data.retry_after_seconds) && response.data.retry_after_seconds > 0 ? response.data.retry_after_seconds : 60;
        notice(`登录尝试过于频繁，请至少等待 ${seconds} 秒再手动尝试。本次未校验密码，也未切换账户。`, "error");
        return;
      }
      if (ticket === epoch) notice(response.code === 401 ? "用户名或密码不正确；未切换账户。" : "登录失败，请检查输入和服务状态。", "error");
    }
  });
});
$("logout-button").addEventListener("click", () => run(async (ticket) => {
  clearResults(); const response = await request("/auth/logout", {});
  if (ticket !== epoch) return;
  if (response.code !== 200) throw new Error("退出未确认，请重试退出操作。");
  setUser(null); $("message").value = ""; $("char-count").textContent = "0";
  signalSessionChange(); notice("已退出，页面中的上次结果已清除。");
}));
document.querySelectorAll("[data-prompt]").forEach((button) => button.addEventListener("click", () => {
  $("message").value = button.dataset.prompt; $("message").dispatchEvent(new Event("input")); $("message").focus();
}));
$("message").addEventListener("input", () => { $("char-count").textContent = String($("message").value.length); });
function showUsage(usage, mode) {
  const n = (value) => Number.isSafeInteger(value) && value >= 0 ? String(value) : "—";
  $("usage").textContent = usage
    ? `Tokens 输入 ${n(usage.prompt_tokens)} / 输出 ${n(usage.completion_tokens)} / 合计 ${n(usage.total_tokens)}`
    : mode === "mock" ? "本地模拟：不消耗模型 tokens" : "模型用量：未提供（不代表免费）";
}
$("chat-form").addEventListener("submit", (event) => {
  event.preventDefault(); const message = $("message").value.trim();
  if (!message || busy || editingAccount) return;
  run(async (ticket) => {
    clearResults(); notice("正在确认身份并处理请求，请勿重复发送…");
    const actor = await currentUser(ticket);
    if (ticket !== epoch) return;
    if (!actor) { notice("请先登录。", "error"); return; }
    const response = await request("/chat", {message});
    if (ticket !== epoch) return;
    if (response.code === 401) { setUser(null); notice("会话已失效，请重新登录。", "error"); return; }
    const data = response.data;
    $("http-status").textContent = `HTTP ${response.code}`;
    $("result-actor").textContent = `${actor.username} · ${roleNames[actor.role] || actor.role}`;
    $("request-id").textContent = data.request_id || response.id || "—";
    showUsage(data.usage, data.mode);
    if (response.code === 429 && data.reason_code === "AI_RATE_LIMIT") {
      $("decision").textContent = "请求限流"; $("decision").className = "badge neutral";
      $("reason").textContent = "AI_RATE_LIMIT";
      $("decision-help").textContent = "这是调用频率限制，不是目标材料的权限决定。";
      $("answer").textContent = "发送过于频繁，本次未调用模型，也未执行工具。";
      $("usage").textContent = "本次限流拒绝：未调用模型";
      const seconds = Number.isSafeInteger(data.retry_after_seconds) && data.retry_after_seconds > 0 ? data.retry_after_seconds : 60;
      notice(`请至少等待 ${seconds} 秒后再手动发送；页面不会自动重试。这不是材料权限拒绝。`, "error");
      return;
    }
    $("tool-call").textContent = data.tool_call ? JSON.stringify(data.tool_call, null, 2) : "没有可展示的工具提议";
    const gateway = data.gateway_result;
    if (gateway && (gateway.decision === "ALLOW" || gateway.decision === "DENY")) {
      $("decision").textContent = gateway.decision; $("decision").className = `badge ${gateway.decision === "ALLOW" ? "allow" : "deny"}`;
      $("reason").textContent = gateway.reason_code;
      const explanations = {
        AUTHORIZED: data.tool_call?.tool_name === "list_applications" ? "允许列出当前账户可见的材料，不代表获准读取所有正文。" : "仅允许上述工具和目标；其他材料仍需单独检查权限。",
        APPLICATION_NOT_FOUND_OR_FORBIDDEN: "目标不存在或当前账户无权访问，系统不区分这两种情况，也不交付正文。",
        INVALID_ARGUMENTS: "工具参数不符合要求，调用被拒绝；不能把它当成资源权限规则已通过验证。",
        TOOL_NOT_ALLOWED: "工具不在允许清单中，调用被拒绝。",
        NOT_AUTHENTICATED: "登录身份无效，调用被拒绝。",
      };
      $("decision-help").textContent = explanations[gateway.reason_code] || "请结合实际工具、目标和原始原因码解读本次决定。";
      $("answer").textContent = typeof data.answer === "string" ? data.answer : "未提供回答";
      notice(gateway.decision === "DENY" ? "网关拒绝：未交付目标材料。请结合实际工具和目标编号解读。" : "网关允许了上述工具调用；不代表允许访问所有材料。", gateway.decision === "DENY" ? "error" : "ok");
    } else {
      $("decision").textContent = response.code >= 400 ? "处理失败" : "无授权决定";
      $("decision").className = `badge ${response.code >= 400 ? "error" : "neutral"}`;
      $("reason").textContent = data.reason_code || data.status || "未获得网关结果";
      $("decision-help").textContent = response.code >= 400 ? "没有可展示的网关决定，不能作为越权被网关拒绝的证据。" : "没有工具调用，不计作网关拦截越权读取。";
      $("answer").textContent = data.answer || data.detail || "没有可交付的结果。";
      notice(response.code >= 400 ? "这不是网关权限拒绝的证据。记录错误码，先不要连续重试。" : "本次没有工具调用，不算网关拦截了越权读取。", response.code >= 400 ? "error" : "");
    }
  });
});
function renderAudit() {
  const query = $("audit-filter").value.trim(); $("audit-rows").replaceChildren();
  const rows = auditRows.filter((row) => !query || row.request_id === query);
  for (const row of rows) {
    const tr = document.createElement("tr");
    const fields = [`${row.timestamp}\n${row.request_id}`, `${row.user_id ?? "—"} · ${row.role ?? "未知"}`,
      `${row.tool_name}\n材料 ${row.application_id ?? "—"}`, `${row.decision}\n${row.execution_status}`, row.reason_code];
    fields.forEach((value) => { const td = document.createElement("td"); td.textContent = value; tr.append(td); });
    $("audit-rows").append(tr);
  }
  $("audit-note").textContent = `显示 ${rows.length} / ${auditRows.length} 条。时间采用日志原始 UTC 时区；编号筛选仅针对本页。`;
}
$("audit-filter").addEventListener("input", renderAudit);
$("audit-button").addEventListener("click", () => run(async (ticket) => {
  auditRows = []; $("audit-rows").replaceChildren();
  const actor = await currentUser(ticket);
  if (ticket !== epoch) return;
  if (actor?.role !== "admin") { notice("审计日志仅允许管理员查看。", "error"); return; }
  const response = await request("/audit/logs?limit=20");
  if (ticket !== epoch) return;
  if (response.code === 401) setUser(null);
  if (response.code !== 200 || !Array.isArray(response.data)) throw new Error("无法读取日志，请确认当前仍是管理员。");
  auditRows = response.data; renderAudit(); notice("日志已加载，没有调用模型。", "ok");
}));
channel?.addEventListener("message", () => { invalidate(); run(async (ticket) => { await currentUser(ticket); if (ticket === epoch) notice("其他页面切换了会话，旧结果已清除。"); }); });
window.addEventListener("pagehide", invalidate);
document.addEventListener("visibilitychange", () => {
  if (document.hidden) { invalidate(); }
  else run(async (ticket) => { await currentUser(ticket); if (ticket === epoch) notice("已重新确认登录状态，旧结果已清除。"); });
});
window.addEventListener("pageshow", (event) => { if (event.persisted) { invalidate(); run(currentUser); } });
run(async (ticket) => {
  const config = await request("/ui/config");
  if (ticket !== epoch) return;
  if (config.code === 200) {
    $("mode").textContent = config.data.mode === "deepseek" ? "DeepSeek · 真实模型" : "Mock · 固定规则";
    $("limits").textContent = config.data.mode === "deepseek" ? "每用户 60 秒 ≤5 次 · 每次启动 ≤20 次尝试 · 输出 ≤128 tokens" : "本地模拟 · 不消耗模型 tokens";
    $("cost-note").textContent = config.data.mode === "deepseek" ? "点击发送后，消息可能发送给 DeepSeek；无关问题也可能消耗额度。不自动重试，请勿输入真实敏感信息。" : "当前为固定规则模拟，无外部模型调用，不消耗模型额度。";
    $("version").textContent = config.data.version;
  }
  const actor = await currentUser(ticket);
  if (ticket === epoch) notice(actor ? "已恢复登录身份。点击示例不会自动发送。" : "请先登录，再发送访问请求。");
});
