/** منطق رابط چت: state گفتگو، رندر پیام‌ها، جریان پاسخ و کارت‌های منبع. */

import { api, streamChat } from "./api.js";

const MAX_HISTORY_MESSAGES = 12;
const SUGGESTIONS = [
  "سیاست مرخصی استعلاجی در سازمان چگونه است؟",
  "برای درخواست مرخصی چه مراحلی باید طی شود؟",
  "مدارک لازم برای تسویه‌حساب پایان همکاری چیست؟",
];

const state = {
  messages: [],
  conversationId: null,
  controller: null,
  streaming: false,
  topK: Number(localStorage.getItem("rag.topK")) || 5,
  diagnostics: [],
};

const els = {
  messages: document.getElementById("messages"),
  emptyState: document.getElementById("empty-state"),
  emptyHint: document.getElementById("empty-hint"),
  suggestions: document.getElementById("suggestions"),
  form: document.getElementById("composer"),
  input: document.getElementById("message-input"),
  sendBtn: document.getElementById("btn-send"),
  stopBtn: document.getElementById("btn-stop"),
  statusDot: document.getElementById("status-dot"),
  statusText: document.getElementById("status-text"),
  themeBtn: document.getElementById("btn-theme"),
  settingsBtn: document.getElementById("btn-settings"),
  settingsPanel: document.getElementById("settings-panel"),
  closeSettings: document.getElementById("btn-close-settings"),
  diagnostics: document.getElementById("settings-diagnostics"),
  topK: document.getElementById("top-k"),
  topKValue: document.getElementById("top-k-value"),
  clearChat: document.getElementById("btn-clear-chat"),
  sidebar: document.getElementById("sidebar"),
  sidebarBtn: document.getElementById("btn-sidebar"),
  sidebarClose: document.getElementById("btn-close-sidebar"),
  backdrop: document.getElementById("sidebar-backdrop"),
};

const toPersianDigits = (value) =>
  String(value).replace(/[0-9]/g, (digit) => "۰۱۲۳۴۵۶۷۸۹"[digit]);

const escapeHtml = (value) =>
  String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");

/* ------------------------------ رندر متن ------------------------------ */

function inlineFormat(text) {
  return text
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`\n]+)`/g, '<code class="inline-code">$1</code>')
    .replace(/\[(\d{1,2})\]/g, '<span class="citation">[$1]</span>');
}

function renderTextBlocks(text) {
  const output = [];
  let list = [];

  const flushList = () => {
    if (!list.length) return;
    output.push(
      `<ul class="bullet-list">${list
        .map((item) => `<li>${inlineFormat(item)}</li>`)
        .join("")}</ul>`,
    );
    list = [];
  };

  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) {
      flushList();
      continue;
    }
    const bullet = trimmed.match(/^[-*•]\s+(.*)$/);
    if (bullet) {
      list.push(bullet[1]);
      continue;
    }
    flushList();
    output.push(`<p>${inlineFormat(trimmed)}</p>`);
  }
  flushList();
  return output.join("");
}

/**
 * رندر امن Markdown سبک: ابتدا escape می‌شود، سپس bold/code/لیست/استناد.
 * هیچ HTML خام از مدل یا کاربر اجرا نمی‌شود.
 */
function renderMarkdown(raw) {
  const escaped = escapeHtml(raw);
  const segments = escaped.split(/```/);
  let html = "";
  segments.forEach((segment, index) => {
    if (index % 2 === 1) {
      html += `<pre class="code-block"><code>${segment.replace(/^[\w-]*\n/, "")}</code></pre>`;
    } else {
      html += renderTextBlocks(segment);
    }
  });
  return html;
}

/* ------------------------------ پیام‌ها ------------------------------ */

function scrollToBottom() {
  els.messages.scrollTop = els.messages.scrollHeight;
}

function updateEmptyState() {
  const hasMessages = state.messages.length > 0;
  els.emptyState.classList.toggle("hidden", hasMessages);
}

function addMessage(role, content) {
  const message = { role, content, sources: [] };
  state.messages.push(message);

  const row = document.createElement("div");
  row.className = `message-row ${role === "user" ? "is-user" : "is-bot"}`;

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = role === "user" ? "شما" : "دانش";

  const bubble = document.createElement("div");
  bubble.className = `bubble ${role === "user" ? "bubble-user" : "bubble-bot"}`;

  const body = document.createElement("div");
  body.className = "bubble-body";
  body.innerHTML = role === "user" ? `<p>${escapeHtml(content)}</p>` : "";

  const sources = document.createElement("div");
  sources.className = "sources hidden";

  bubble.append(body, sources);
  row.append(avatar, bubble);
  els.messages.appendChild(row);
  updateEmptyState();
  scrollToBottom();

  return { message, row, body, sources };
}

function renderSources(container, sources) {
  container.innerHTML = "";
  if (!sources || !sources.length) {
    container.classList.add("hidden");
    return;
  }
  container.classList.remove("hidden");

  const title = document.createElement("div");
  title.className = "sources-title";
  title.textContent = `منابع (${toPersianDigits(sources.length)})`;
  container.appendChild(title);

  const grid = document.createElement("div");
  grid.className = "sources-grid";

  sources.forEach((source, index) => {
    const card = document.createElement("details");
    card.className = "source-card";

    const summary = document.createElement("summary");
    const badge = document.createElement("span");
    badge.className = "source-index";
    badge.textContent = toPersianDigits(index + 1);

    const name = document.createElement("span");
    name.className = "source-name";
    name.textContent =
      source.filename + (source.page ? ` — صفحه ${toPersianDigits(source.page)}` : "");

    const score = document.createElement("span");
    score.className = "source-score";
    score.textContent = `${toPersianDigits(Math.round((source.score || 0) * 100))}٪`;

    summary.append(badge, name, score);

    const snippet = document.createElement("p");
    snippet.className = "source-snippet";
    snippet.textContent = source.snippet || "";

    card.append(summary, snippet);
    grid.appendChild(card);
  });

  container.appendChild(grid);
}

/* ------------------------------ جریان پاسخ ------------------------------ */

function setStreamingUI(active) {
  state.streaming = active;
  els.stopBtn.classList.toggle("hidden", !active);
  els.sendBtn.classList.toggle("hidden", active);
  els.input.disabled = active;
}

async function sendMessage(rawText) {
  const question = String(rawText || "").trim();
  if (!question || state.streaming) return;

  const history = state.messages
    .filter((message) => message.content)
    .slice(-MAX_HISTORY_MESSAGES)
    .map(({ role, content }) => ({ role, content }));

  addMessage("user", question);
  const bot = addMessage("assistant", "");
  bot.body.innerHTML = '<span class="typing"><i></i><i></i><i></i></span>';
  scrollToBottom();

  state.controller = new AbortController();
  setStreamingUI(true);

  let answer = "";
  let sources = [];
  let painted = false;

  const paint = () => {
    painted = false;
    bot.body.innerHTML =
      renderMarkdown(answer) + (state.streaming ? '<span class="caret"></span>' : "");
    scrollToBottom();
  };
  const schedulePaint = () => {
    if (painted) return;
    painted = true;
    requestAnimationFrame(paint);
  };

  try {
    for await (const { event, data } of streamChat(
      {
        message: question,
        history,
        conversation_id: state.conversationId,
        top_k: state.topK,
      },
      state.controller.signal,
    )) {
      if (event === "open") {
        if (data.conversation_id) state.conversationId = data.conversation_id;
      } else if (event === "sources") {
        sources = data.sources || [];
        renderSources(bot.sources, sources);
        bot.message.sources = sources;
      } else if (event === "token") {
        answer += data.delta || "";
        schedulePaint();
      } else if (event === "error") {
        throw new Error(data.message || "خطا در دریافت پاسخ.");
      } else if (event === "done" && data.conversation_id) {
        state.conversationId = data.conversation_id;
      }
    }

    bot.message.content = answer;
    if (!answer.trim()) {
      answer = "پاسخی از مدل دریافت نشد.";
      bot.message.content = answer;
    }
  } catch (error) {
    if (error.name === "AbortError") {
      answer = (answer ? answer + "\n\n" : "") + "_پاسخ متوقف شد._";
      bot.message.content = answer;
    } else {
      bot.message.content = "";
      bot.row.classList.add("is-error");
      bot.body.innerHTML = `<p class="error-text">${escapeHtml(error.message || "خطای نامشخص")}</p>`;
    }
  } finally {
    setStreamingUI(false);
    if (!bot.row.classList.contains("is-error")) {
      bot.body.innerHTML = renderMarkdown(answer) || "<p>…</p>";
    }
    state.controller = null;
    scrollToBottom();
    els.input.focus();
  }
}

/* ------------------------------ سلامت سرویس ------------------------------ */

function setStatus(ok, diagnostics = []) {
  state.diagnostics = diagnostics;
  els.statusDot.className = `status-dot ${ok ? "is-ok" : "is-warn"}`;
  els.statusText.textContent = ok ? "آنلاین" : "نیازمند تنظیم";
  els.diagnostics.innerHTML = "";
  if (!diagnostics.length) {
    const li = document.createElement("li");
    li.className = "diagnostic-ok";
    li.textContent = "همه‌چیز آماده است.";
    els.diagnostics.appendChild(li);
    return;
  }
  for (const text of diagnostics) {
    const li = document.createElement("li");
    li.textContent = text;
    els.diagnostics.appendChild(li);
  }
}

async function refreshHealth() {
  try {
    const health = await api.health();
    setStatus(health.status === "ok", health.diagnostics || []);
  } catch {
    setStatus(false, ["اتصال به سرور برقرار نشد؛ مطمئن شوید سرویس بک‌اند اجراست."]);
  }
}

/* ------------------------------ تنظیمات و تم ------------------------------ */

function applyTopK(value) {
  state.topK = Math.min(10, Math.max(1, Number(value) || 5));
  localStorage.setItem("rag.topK", String(state.topK));
  els.topK.value = String(state.topK);
  els.topKValue.textContent = toPersianDigits(state.topK);
}

function setSettingsOpen(open) {
  els.settingsPanel.classList.toggle("hidden", !open);
  els.settingsBtn.setAttribute("aria-expanded", String(open));
}

function applyTheme(theme) {
  const dark = theme === "dark";
  document.documentElement.classList.toggle("dark", dark);
  localStorage.setItem("rag.theme", dark ? "dark" : "light");
}

function toggleSidebar(open) {
  els.sidebar.classList.toggle("is-open", open);
  els.backdrop.classList.toggle("hidden", !open);
}

/* ------------------------------ رویدادها ------------------------------ */

function autoGrow() {
  els.input.style.height = "auto";
  els.input.style.height = `${Math.min(els.input.scrollHeight, 180)}px`;
}

els.form.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = els.input.value;
  els.input.value = "";
  autoGrow();
  sendMessage(text);
});

els.input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    els.form.requestSubmit();
  }
});

els.input.addEventListener("input", autoGrow);

els.stopBtn.addEventListener("click", () => {
  if (state.controller) state.controller.abort();
});

els.themeBtn.addEventListener("click", () => {
  const isDark = document.documentElement.classList.contains("dark");
  applyTheme(isDark ? "light" : "dark");
});

els.settingsBtn.addEventListener("click", () => {
  setSettingsOpen(els.settingsPanel.classList.contains("hidden"));
});

els.closeSettings.addEventListener("click", () => setSettingsOpen(false));

els.topK.addEventListener("input", (event) => applyTopK(event.target.value));

els.clearChat.addEventListener("click", () => {
  state.messages = [];
  state.conversationId = null;
  els.messages.querySelectorAll(".message-row").forEach((row) => row.remove());
  updateEmptyState();
  setSettingsOpen(false);
});

els.sidebarBtn.addEventListener("click", () => toggleSidebar(true));
els.sidebarClose.addEventListener("click", () => toggleSidebar(false));
els.backdrop.addEventListener("click", () => toggleSidebar(false));

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    setSettingsOpen(false);
    toggleSidebar(false);
  }
});

window.addEventListener("documents:updated", (event) => {
  const documents = event.detail || [];
  if (!documents.length) {
    els.emptyHint.textContent =
      "هنوز سندی ایندکس نشده است؛ از پنل «اسناد دانش» اولین سند سازمانی را آپلود کنید.";
  } else {
    els.emptyHint.textContent =
      "پاسخ‌ها همراه با منبع (نام سند و شماره صفحه) نمایش داده می‌شوند.";
  }
});

/* ------------------------------ راه‌اندازی ------------------------------ */

function buildSuggestions() {
  els.suggestions.innerHTML = "";
  for (const text of SUGGESTIONS) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "suggestion";
    button.textContent = text;
    button.addEventListener("click", () => sendMessage(text));
    els.suggestions.appendChild(button);
  }
}

function init() {
  applyTheme(localStorage.getItem("rag.theme") || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));
  applyTopK(state.topK);
  buildSuggestions();
  updateEmptyState();
  refreshHealth();
  setInterval(refreshHealth, 30000);
  els.input.focus();
}

init();
