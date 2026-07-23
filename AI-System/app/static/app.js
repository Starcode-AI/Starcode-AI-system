"use strict";

const state = {
  user: null,
  language: localStorage.getItem("localai-language") || (navigator.language.toLowerCase().startsWith("de") ? "de" : "en"),
  translations: {},
  conversationId: null,
  streaming: false,
  controller: null,
  jobTimer: null
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

function element(tag, options = {}, children = []) {
  const node = document.createElement(tag);
  if (options.className) node.className = options.className;
  if (options.text !== undefined) node.textContent = String(options.text);
  if (options.title) node.title = options.title;
  if (options.type) node.type = options.type;
  if (options.href) node.href = options.href;
  if (options.target) node.target = options.target;
  if (options.rel) node.rel = options.rel;
  if (options.dataset) Object.assign(node.dataset, options.dataset);
  if (options.attrs) Object.entries(options.attrs).forEach(([key, value]) => node.setAttribute(key, value));
  const list = Array.isArray(children) ? children : [children];
  list.filter(Boolean).forEach(child => node.append(child));
  return node;
}

function text(key, fallback = key) {
  return key.split(".").reduce((value, part) => value?.[part], state.translations) ?? fallback;
}

async function loadLanguage() {
  try {
    const response = await fetch(`/assets/i18n/${state.language}.json`, {cache: "no-store"});
    state.translations = await response.json();
  } catch {
    state.translations = {};
  }
  document.documentElement.lang = state.language;
  $$('[data-i18n]').forEach(node => {
    const value = text(node.dataset.i18n, node.textContent);
    if (value.includes("<br>")) {
      const parts = value.split("<br>");
      node.replaceChildren(...parts.flatMap((part, index) => index ? [document.createElement("br"), document.createTextNode(part)] : [document.createTextNode(part)]));
    } else {
      node.textContent = value;
    }
  });
  $$('[data-i18n-placeholder]').forEach(node => node.placeholder = text(node.dataset.i18nPlaceholder, node.placeholder));
}

function cookie(name) {
  const match = document.cookie.split("; ").find(item => item.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : "";
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (!(options.body instanceof FormData) && options.body !== undefined && typeof options.body !== "string") {
    headers.set("Content-Type", "application/json");
    options.body = JSON.stringify(options.body);
  }
  const csrf = cookie("localai_csrf");
  if (csrf && !["GET", "HEAD"].includes((options.method || "GET").toUpperCase())) headers.set("X-CSRF-Token", csrf);
  const response = await fetch(path, {...options, headers, credentials: "same-origin"});
  if (response.status === 401) {
    state.user = null;
    showLogin();
  }
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try { detail = (await response.json()).detail || detail; } catch { detail = response.statusText || detail; }
    throw new Error(detail);
  }
  const type = response.headers.get("content-type") || "";
  return type.includes("application/json") ? response.json() : response;
}

function toast(message, kind = "info") {
  const node = element("div", {className: `toast ${kind}`, text: message});
  $("#toastRegion").append(node);
  setTimeout(() => node.remove(), 4500);
}

function formatBytes(bytes = 0) {
  if (!Number.isFinite(Number(bytes))) return "—";
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  let value = Number(bytes), index = 0;
  while (value >= 1024 && index < units.length - 1) { value /= 1024; index += 1; }
  return `${value.toFixed(index ? 1 : 0)} ${units[index]}`;
}

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : new Intl.DateTimeFormat(state.language, {dateStyle: "medium", timeStyle: "short"}).format(date);
}

function roleLabel(role) {
  const labels = state.language === "de"
    ? {user: "Benutzer", moderator: "Moderator", administrator: "Administrator", system_administrator: "Systemadministrator"}
    : {user: "User", moderator: "Moderator", administrator: "Administrator", system_administrator: "System administrator"};
  return labels[role] || role;
}

function showLogin() {
  $("#loginView").hidden = false;
  $("#appView").hidden = true;
}

function showApp() {
  $("#loginView").hidden = true;
  $("#appView").hidden = false;
  const name = state.user.display_name || state.user.email;
  $("#profileName").textContent = name;
  $("#profileRole").textContent = roleLabel(state.user.role);
  $("#profileInitials").textContent = name.split(/\s+/).slice(0, 2).map(part => part[0]).join("").toUpperCase();
  $("#adminNav").hidden = !["administrator", "system_administrator"].includes(state.user.role);
}

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("localai-theme", theme);
}

async function toggleLanguage() {
  state.language = state.language === "de" ? "en" : "de";
  localStorage.setItem("localai-language", state.language);
  await loadLanguage();
  if (state.user) navigate();
}

function pageName(page) {
  const keys = {chat: "nav.chat", research: "nav.research", files: "nav.files", projects: "nav.projects", knowledge: "nav.knowledge", history: "nav.history", settings: "nav.settings", admin: "nav.admin"};
  return text(keys[page] || keys.chat, page);
}

async function navigate() {
  if (!state.user) return;
  let page = location.hash.replace(/^#/, "").split("/")[0] || "chat";
  if (page === "admin" && !["administrator", "system_administrator"].includes(state.user.role)) page = "chat";
  $$('[data-page-section]').forEach(node => node.hidden = node.dataset.pageSection !== page);
  $$('[data-page]').forEach(node => node.classList.toggle("active", node.dataset.page === page));
  $("#pageTitle").textContent = pageName(page);
  $("#pageEyebrow").textContent = page === "admin" ? "SYSTEM CONTROL" : "LOCAL WORKSPACE";
  $("#sidebar").classList.remove("open");
  if (page !== "projects" && state.jobTimer) { clearInterval(state.jobTimer); state.jobTimer = null; }
  const loaders = {files: loadFiles, projects: loadJobs, knowledge: loadKnowledge, history: loadHistory, settings: loadSessions, admin: loadAdmin};
  if (loaders[page]) loaders[page]().catch(error => toast(error.message, "error"));
}

function renderRichText(content) {
  const fragment = document.createDocumentFragment();
  const segments = content.split(/```([\w.+#-]*)\n?([\s\S]*?)```/g);
  for (let index = 0; index < segments.length; index += 3) {
    appendTextBlock(fragment, segments[index] || "");
    const code = segments[index + 2];
    if (code !== undefined) {
      const pre = element("pre");
      const codeNode = element("code", {text: code.replace(/\n$/, "")});
      if (segments[index + 1]) codeNode.dataset.language = segments[index + 1];
      pre.append(codeNode);
      fragment.append(pre);
    }
  }
  return fragment;
}

function appendTextBlock(parent, block) {
  const lines = block.split("\n");
  let list = null;
  let index = 0;
  while (index < lines.length) {
    const line = lines[index].trimEnd();
    if (!line.trim()) { list = null; index += 1; continue; }
    if (line.includes("|") && index + 1 < lines.length && /^\s*\|?\s*:?-+/.test(lines[index + 1])) {
      const table = element("table");
      const rows = [];
      rows.push(line);
      index += 2;
      while (index < lines.length && lines[index].includes("|")) { rows.push(lines[index]); index += 1; }
      rows.forEach((row, rowIndex) => {
        const tr = element("tr");
        row.replace(/^\||\|$/g, "").split("|").forEach(cell => tr.append(element(rowIndex ? "td" : "th", {text: cell.trim()})));
        table.append(tr);
      });
      parent.append(table);
      list = null;
      continue;
    }
    const heading = line.match(/^(#{1,4})\s+(.+)/);
    if (heading) {
      parent.append(element(`h${Math.min(heading[1].length + 2, 6)}`, {text: heading[2]}));
      list = null; index += 1; continue;
    }
    const bullet = line.match(/^[-*]\s+(.+)/);
    if (bullet) {
      if (!list) { list = element("ul"); parent.append(list); }
      list.append(element("li", {text: bullet[1]}));
      index += 1; continue;
    }
    const numbered = line.match(/^\d+[.)]\s+(.+)/);
    if (numbered) {
      if (!list || list.tagName !== "OL") { list = element("ol"); parent.append(list); }
      list.append(element("li", {text: numbered[1]}));
      index += 1; continue;
    }
    parent.append(element("p", {text: line}));
    list = null; index += 1;
  }
}

function addMessage(role, content, options = {}) {
  $("#chatEmpty").hidden = true;
  $("#messages").hidden = false;
  const article = element("article", {className: `message ${role}`});
  if (options.id) article.dataset.messageId = options.id;
  const avatar = element("span", {className: "message-avatar", text: role === "assistant" ? "AI" : (state.user?.display_name?.[0] || "U")});
  const body = element("div");
  const head = element("div", {className: "message-head"}, [
    element("strong", {text: role === "assistant" ? "LocalAI" : state.user?.display_name || "You"}),
    element("time", {text: options.time ? formatDate(options.time) : new Intl.DateTimeFormat(state.language, {timeStyle: "short"}).format(new Date())})
  ]);
  const contentNode = element("div", {className: "message-content"});
  contentNode.append(renderRichText(content));
  body.append(head, contentNode);
  if (role === "assistant") {
    const actions = element("div", {className: "message-actions"});
    const copy = element("button", {text: "⧉", title: state.language === "de" ? "Kopieren" : "Copy", dataset: {messageAction: "copy"}});
    actions.append(copy);
    if (options.id) {
      actions.append(
        element("button", {text: "↑", title: "Helpful", dataset: {messageAction: "up"}}),
        element("button", {text: "↓", title: "Not helpful", dataset: {messageAction: "down"}})
      );
    }
    body.append(actions);
  }
  if (options.sources?.length) body.append(renderSources(options.sources));
  article.append(avatar, body);
  $("#messages").append(article);
  article.scrollIntoView({behavior: "smooth", block: "end"});
  return {article, contentNode, body};
}

function renderSources(sources) {
  const list = element("div", {className: "source-list"});
  sources.forEach(source => {
    try {
      const url = new URL(source.url);
      if (url.protocol !== "https:") return;
      const link = element("a", {href: url.href, target: "_blank", rel: "noopener noreferrer"}, [
        element("span", {text: `[${source.index}] ${source.title}`}),
        element("small", {text: source.domain})
      ]);
      list.append(link);
    } catch { /* invalid source is not rendered */ }
  });
  return list;
}

async function loadRecent() {
  const conversations = await api("/api/conversations");
  const root = $("#recentChats");
  root.replaceChildren();
  conversations.slice(0, 8).forEach(item => {
    const button = element("button", {text: item.title, dataset: {conversationId: item.id}});
    button.addEventListener("click", () => openConversation(item.id));
    root.append(button);
  });
}

async function openConversation(id) {
  const conversation = await api(`/api/conversations/${encodeURIComponent(id)}`);
  state.conversationId = id;
  location.hash = "chat";
  $("#messages").replaceChildren();
  $("#chatEmpty").hidden = conversation.messages.length > 0;
  conversation.messages.forEach(message => {
    let sources = [];
    try { sources = JSON.parse(message.sources_json || "[]"); } catch { sources = []; }
    addMessage(message.role, message.content, {id: message.id, sources, time: message.created_at});
  });
}

function newChat() {
  state.conversationId = null;
  location.hash = "chat";
  $("#messages").replaceChildren();
  $("#messages").hidden = false;
  $("#chatEmpty").hidden = false;
  $("#chatInput").focus();
}

async function sendChat(event) {
  event.preventDefault();
  if (state.streaming) return;
  const input = $("#chatInput");
  const message = input.value.trim();
  if (!message) return;
  input.value = ""; resizeComposer();
  addMessage("user", message);
  const assistant = addMessage("assistant", "");
  const statusNode = element("p", {className: "muted", text: state.language === "de" ? "Wird vorbereitet …" : "Preparing …"});
  assistant.contentNode.append(statusNode);
  state.streaming = true;
  state.controller = new AbortController();
  $("#sendButton").hidden = true;
  $("#stopButton").hidden = false;
  try {
    const headers = {"Content-Type": "application/json", "X-CSRF-Token": cookie("localai_csrf")};
    const response = await fetch("/api/chat", {
      method: "POST", headers, credentials: "same-origin", signal: state.controller.signal,
      body: JSON.stringify({conversation_id: state.conversationId, message, research: $("#researchToggle").checked})
    });
    if (!response.ok) throw new Error((await response.json()).detail || `HTTP ${response.status}`);
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "", answer = "", messageId = null, sources = [];
    while (true) {
      const {value, done} = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, {stream: true});
      const frames = buffer.split("\n\n");
      buffer = frames.pop() || "";
      for (const frame of frames) {
        const eventLine = frame.split("\n").find(line => line.startsWith("event:"));
        const dataLine = frame.split("\n").find(line => line.startsWith("data:"));
        if (!dataLine) continue;
        const type = eventLine ? eventLine.slice(6).trim() : "message";
        const data = JSON.parse(dataLine.slice(5).trim());
        if (type === "meta") state.conversationId = data.conversation_id;
        if (type === "status") statusNode.textContent = data.message;
        if (type === "warning") toast(data.message, "error");
        if (type === "blocked") { answer = data.message; messageId = data.message_id; }
        if (type === "chunk") answer += data.text;
        if (type === "error") throw new Error(data.message);
        if (type === "done") { messageId = data.message_id; sources = data.sources || []; }
        if (["chunk", "blocked"].includes(type)) {
          assistant.contentNode.replaceChildren(renderRichText(answer));
          assistant.article.scrollIntoView({block: "end"});
        }
      }
    }
    if (!answer) assistant.contentNode.replaceChildren(element("p", {text: state.language === "de" ? "Keine Antwort erhalten." : "No response received."}));
    if (messageId) {
      assistant.article.dataset.messageId = messageId;
      const actions = $(".message-actions", assistant.body);
      if (actions && actions.children.length === 1) actions.append(
        element("button", {text: "↑", title: "Helpful", dataset: {messageAction: "up"}}),
        element("button", {text: "↓", title: "Not helpful", dataset: {messageAction: "down"}})
      );
    }
    if (sources.length) assistant.body.append(renderSources(sources));
    await loadRecent();
  } catch (error) {
    if (error.name === "AbortError") assistant.contentNode.replaceChildren(element("p", {className: "muted", text: state.language === "de" ? "Antwort gestoppt." : "Response stopped."}));
    else { assistant.contentNode.replaceChildren(element("p", {text: error.message})); toast(error.message, "error"); }
  } finally {
    state.streaming = false;
    state.controller = null;
    $("#sendButton").hidden = false;
    $("#stopButton").hidden = true;
  }
}

function resizeComposer() {
  const input = $("#chatInput");
  $("#contextMeter").textContent = `${Math.ceil(input.value.length / 4)} / 8k`;
}

async function runResearch(event) {
  event.preventDefault();
  const query = $("#researchQuery").value.trim();
  const root = $("#researchResult");
  root.className = "result-area loading";
  root.replaceChildren(element("p", {className: "muted", text: state.language === "de" ? "Quellen werden gesucht, geladen und geprüft …" : "Searching, loading, and checking sources …"}));
  try {
    const result = await api("/api/research", {method: "POST", body: {query}});
    root.className = "result-area";
    const answer = element("div", {className: "research-answer"});
    answer.append(renderRichText(result.answer));
    root.replaceChildren(answer);
    if (result.sources?.length) {
      const sources = element("div", {className: "research-sources"});
      result.sources.forEach(source => {
        const card = element("a", {className: "source-card", href: source.url, target: "_blank", rel: "noopener noreferrer"}, [
          element("small", {text: `[${source.index}] ${source.trust.toUpperCase()}`}),
          element("strong", {text: source.title}),
          element("span", {text: `${source.domain} · ${source.published_at || "date unknown"}`})
        ]);
        sources.append(card);
      });
      root.append(sources);
    }
  } catch (error) {
    root.className = "result-area";
    root.replaceChildren(element("p", {text: error.message}));
    toast(error.message, "error");
  }
}

async function analyzeFile(file) {
  if (!file) return;
  const form = new FormData(); form.append("file", file);
  const root = $("#fileResult");
  root.hidden = false; root.className = "result-area loading";
  root.replaceChildren(element("p", {text: state.language === "de" ? "Datei wird sicher eingelesen und geprüft …" : "Reading and checking file safely …"}));
  try {
    const result = await api("/api/files/analyze", {method: "POST", body: form});
    root.className = "result-area";
    const analysis = result.analysis || {};
    root.replaceChildren(
      element("div", {className: "section-head"}, [element("h3", {text: result.filename}), element("span", {className: `status-tag ${analysis.safe === false ? "failed" : "completed"}`, text: analysis.safe === false ? "CHECK" : "ANALYZED"})]),
      element("p", {className: "muted", text: `${formatBytes(result.size)} · ${result.mime} · SHA-256 ${result.sha256}`}),
      element("p", {text: fileAnalysisSummary(result)})
    );
    if (analysis.code_review?.findings?.length) {
      const list = element("ul");
      analysis.code_review.findings.slice(0, 20).forEach(item => list.append(element("li", {text: `${item.severity.toUpperCase()} · Line ${item.line}: ${item.message}`})));
      root.append(element("h4", {text: "Code review"}), list);
    }
    await loadFiles();
  } catch (error) {
    root.className = "result-area"; root.replaceChildren(element("p", {text: error.message})); toast(error.message, "error");
  }
}

function fileAnalysisSummary(result) {
  const analysis = result.analysis || {};
  if (result.executable) return state.language === "de" ? "Ausführbare Datei wurde unter Quarantänebedingungen gespeichert und nicht ausgeführt." : "Executable file was quarantined and not executed.";
  if (analysis.type === "pdf") return `PDF · ${analysis.page_count || 0} pages${analysis.encrypted ? " · encrypted" : ""}`;
  if (analysis.type === "archive") return `${analysis.file_count || 0} files · expanded ${formatBytes(analysis.expanded_bytes)}${analysis.issues?.length ? ` · ${analysis.issues.join("; ")}` : ""}`;
  if (analysis.type === "text") return `${analysis.line_count || 0} lines${analysis.prompt_injection_detected ? " · prompt injection indicators removed" : ""}`;
  return analysis.message || analysis.error || "Binary file inspected without execution.";
}

async function loadFiles() {
  const items = await api("/api/files");
  const root = $("#fileList"); root.replaceChildren();
  if (!items.length) { root.append(element("p", {className: "muted", text: state.language === "de" ? "Noch keine Dateien analysiert." : "No files analyzed yet."})); return; }
  items.forEach(item => {
    const card = element("article", {className: "list-card"}, [
      element("div", {}, [element("strong", {text: item.filename}), element("small", {text: `${formatBytes(item.size)} · ${formatDate(item.uploaded_at)}`})]),
      element("div", {className: "actions"}, [element("span", {className: `status-tag ${item.executable ? "failed" : "completed"}`, text: item.executable ? "QUARANTINE" : "SAFE READ"}), element("button", {className: "text-button", text: "×", dataset: {deleteFile: item.id}})])
    ]);
    root.append(card);
  });
}

async function createProject(event) {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.currentTarget));
  try {
    await api("/api/projects/generate", {method: "POST", body: data});
    toast(state.language === "de" ? "Projektaufgabe gestartet." : "Project job started.");
    await loadJobs();
  } catch (error) { toast(error.message, "error"); }
}

async function loadJobs() {
  const jobs = await api("/api/projects/jobs");
  const root = $("#jobList"); root.replaceChildren();
  let active = false;
  jobs.forEach(job => {
    active ||= ["queued", "running", "reviewing"].includes(job.status);
    const info = job.result_json && job.result_json !== "{}" ? JSON.parse(job.result_json) : {};
    const actions = [element("span", {className: `status-tag ${job.status}`, text: job.status})];
    if (job.status === "completed") actions.push(element("a", {className: "button secondary", text: text("common.download", "Download"), href: `/api/projects/jobs/${job.id}/download`}));
    if (["queued", "running", "reviewing"].includes(job.status)) actions.push(element("button", {className: "text-button", text: "Cancel", dataset: {cancelJob: job.id}}));
    const progressStep = Math.round(Math.max(0, Math.min(100, job.progress)) / 10) * 10;
    root.append(element("article", {className: "list-card"}, [
      element("div", {}, [element("strong", {text: info.name || (state.language === "de" ? "Projekterstellung" : "Project generation")}), element("small", {text: job.error_message || formatDate(job.created_at)}), element("div", {className: "progress"}, element("i", {className: `p-${progressStep}`}))]),
      element("div", {className: "actions"}, actions)
    ]));
  });
  if (!jobs.length) root.append(element("p", {className: "muted", text: state.language === "de" ? "Noch keine Projekte erzeugt." : "No projects generated yet."}));
  if (active && !state.jobTimer) state.jobTimer = setInterval(() => loadJobs().catch(() => {}), 3000);
  if (!active && state.jobTimer) { clearInterval(state.jobTimer); state.jobTimer = null; }
}

async function loadKnowledge() {
  const q = $("#knowledgeSearch").value.trim();
  const category = $("#knowledgeCategory").value;
  const items = await api(`/api/knowledge?q=${encodeURIComponent(q)}&category=${encodeURIComponent(category)}`);
  const root = $("#knowledgeList"); root.replaceChildren();
  items.forEach(item => root.append(element("article", {className: "knowledge-card"}, [
    element("header", {}, [element("span", {className: `status-tag ${item.category}`, text: item.category}), element("small", {text: `${Math.round(item.confidence * 100)}%`})]),
    element("h3", {text: item.title}), element("p", {text: item.content}),
    element("footer", {}, [element("span", {text: item.source || "Local note"}), element("span", {text: `v${item.version}`})])
  ])));
  if (!items.length) root.append(element("p", {className: "muted", text: state.language === "de" ? "Keine passenden Wissenseinträge." : "No matching knowledge entries."}));
}

async function createKnowledge(event) {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.currentTarget));
  data.confidence = data.category === "researched" ? 0.5 : 0.2;
  try { await api("/api/knowledge", {method: "POST", body: data}); $("#knowledgeDialog").close(); event.currentTarget.reset(); await loadKnowledge(); toast(text("common.save", "Saved")); }
  catch (error) { toast(error.message, "error"); }
}

async function loadHistory() {
  const q = $("#historySearch").value.trim();
  const archived = $("#archiveFilter").checked;
  const items = await api(`/api/conversations?archived=${archived}&q=${encodeURIComponent(q)}`);
  const root = $("#historyList"); root.replaceChildren();
  items.forEach(item => root.append(element("article", {className: "list-card"}, [
    element("div", {}, [element("strong", {text: item.title}), element("small", {text: `${item.messages.length} messages · ${formatDate(item.updated_at)}`})]),
    element("div", {className: "actions"}, [element("button", {className: "text-button", text: text("common.open", "Open"), dataset: {openConversation: item.id}}), element("button", {className: "text-button", text: archived ? "Restore" : text("common.archive", "Archive"), dataset: {archiveConversation: item.id, archiveState: String(!archived)}}), element("button", {className: "text-button", text: text("common.delete", "Delete"), dataset: {deleteConversation: item.id}})])
  ])));
  if (!items.length) root.append(element("p", {className: "muted", text: state.language === "de" ? "Keine Unterhaltungen gefunden." : "No conversations found."}));
}

async function loadSessions() {
  const items = await api("/api/auth/sessions");
  const root = $("#sessionList"); root.replaceChildren();
  items.forEach(item => root.append(element("article", {className: "list-card"}, [
    element("div", {}, [element("strong", {text: item.current ? (state.language === "de" ? "Dieses Gerät" : "This device") : item.user_agent || "Unknown device"}), element("small", {text: `${item.ip_address} · ${formatDate(item.last_seen_at)}`})]),
    item.current ? element("span", {className: "status-tag completed", text: "CURRENT"}) : element("button", {className: "text-button", text: "End", dataset: {endSession: item.id}})
  ])));
}

async function loadAdmin() {
  const [status, models, events] = await Promise.all([api("/api/admin/status"), api("/api/admin/models"), api("/api/admin/security-events")]);
  const metrics = [
    ["CPU", `${status.cpu_percent}%`], ["RAM", `${status.memory.percent}%`], ["Disk", `${status.disk.percent}%`], ["Users", status.counts.users]
  ];
  const statusRoot = $("#statusCards"); statusRoot.replaceChildren();
  metrics.forEach(([label, value]) => statusRoot.append(element("article", {className: "metric-card"}, [element("small", {text: label}), element("strong", {text: value})])));
  const modelRoot = $("#modelList"); modelRoot.replaceChildren();
  models.profiles.forEach(model => modelRoot.append(element("article", {className: "list-card"}, [element("div", {}, [element("strong", {text: model.name}), element("small", {text: `${model.model_name} · ${model.context_length} ctx`})]), model.is_active ? element("span", {className: "status-tag completed", text: "ACTIVE"}) : element("button", {className: "text-button", text: "Activate", dataset: {activateModel: model.id}})])));
  const eventRoot = $("#securityList"); eventRoot.replaceChildren();
  events.slice(0, 30).forEach(item => eventRoot.append(element("article", {className: `event ${item.severity}`}, [element("strong", {text: item.type}), element("p", {text: item.summary}), element("small", {text: formatDate(item.created_at)})])));
  if (!events.length) eventRoot.append(element("p", {className: "muted", text: "No security events."}));
  updateModelPill(status.model_service);
}

function updateModelPill(modelService) {
  const pill = $("#modelState");
  const dot = $(".status-dot", pill);
  dot.classList.toggle("offline", !modelService.available);
  $("span", pill).textContent = modelService.available ? `${modelService.models.length} local model${modelService.models.length === 1 ? "" : "s"}` : "Model offline";
}

async function checkModel() {
  if (!["administrator", "system_administrator"].includes(state.user.role)) {
    $("#modelState span").textContent = state.language === "de" ? "Lokales Modell" : "Local model";
    return;
  }
  try { const status = await api("/api/admin/status"); updateModelPill(status.model_service); } catch { $("#modelState .status-dot").classList.add("offline"); }
}

async function handleDelegatedClick(event) {
  const target = event.target.closest("button, a");
  if (!target) return;
  if (target.dataset.action === "theme") setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
  if (target.dataset.action === "language") await toggleLanguage();
  if (target.dataset.action === "open-sidebar") $("#sidebar").classList.add("open");
  if (target.dataset.action === "close-sidebar") $("#sidebar").classList.remove("open");
  if (target.dataset.action === "go-files") location.hash = "files";
  if (target.dataset.action === "refresh-files") await loadFiles();
  if (target.dataset.action === "refresh-jobs") await loadJobs();
  if (target.dataset.action === "refresh-sessions") await loadSessions();
  if (target.dataset.action === "refresh-admin") await loadAdmin();
  if (target.dataset.openConversation) await openConversation(target.dataset.openConversation);
  if (target.dataset.archiveConversation) { await api(`/api/conversations/${target.dataset.archiveConversation}`, {method: "PATCH", body: {archived: target.dataset.archiveState === "true"}}); await loadHistory(); await loadRecent(); }
  if (target.dataset.deleteConversation && confirm(state.language === "de" ? "Unterhaltung endgültig löschen?" : "Permanently delete conversation?")) { await api(`/api/conversations/${target.dataset.deleteConversation}`, {method: "DELETE"}); await loadHistory(); await loadRecent(); }
  if (target.dataset.deleteFile && confirm(state.language === "de" ? "Datei und Analyse löschen?" : "Delete file and analysis?")) { await api(`/api/files/${target.dataset.deleteFile}`, {method: "DELETE"}); await loadFiles(); }
  if (target.dataset.cancelJob) { await api(`/api/projects/jobs/${target.dataset.cancelJob}/cancel`, {method: "POST"}); await loadJobs(); }
  if (target.dataset.endSession) { await api(`/api/auth/sessions/${target.dataset.endSession}`, {method: "DELETE"}); await loadSessions(); }
  if (target.dataset.activateModel) { await api(`/api/admin/models/${target.dataset.activateModel}/activate`, {method: "POST"}); await loadAdmin(); }
  if (target.dataset.messageAction) {
    const message = target.closest(".message");
    if (target.dataset.messageAction === "copy") { await navigator.clipboard.writeText($(".message-content", message).textContent); toast(state.language === "de" ? "Kopiert." : "Copied."); }
    if (["up", "down"].includes(target.dataset.messageAction) && message.dataset.messageId) { await api("/api/feedback", {method: "POST", body: {message_id: message.dataset.messageId, rating: target.dataset.messageAction === "up" ? 1 : -1, category: "quick_rating", comment: ""}}); toast(state.language === "de" ? "Feedback gespeichert." : "Feedback saved."); }
  }
}

async function boot() {
  setTheme(localStorage.getItem("localai-theme") || (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark"));
  await loadLanguage();
  try {
    state.user = await api("/api/auth/me");
    showApp(); await loadRecent(); await checkModel(); navigate();
  } catch {
    showLogin();
    try {
      const setup = await api("/api/setup/status");
      if (!setup.configured) {
        const hint = $("#setupHint"); hint.hidden = false;
        hint.textContent = state.language === "de" ? "Noch kein Konto vorhanden. Führe zuerst das Admin-Einrichtungsskript aus." : "No account exists yet. Run the administrator setup script first.";
      }
    } catch { /* login view remains usable */ }
  }
}

$("#loginForm").addEventListener("submit", async event => {
  event.preventDefault();
  const button = $("button[type=submit]", event.currentTarget); button.disabled = true;
  try {
    state.user = await api("/api/auth/login", {method: "POST", body: Object.fromEntries(new FormData(event.currentTarget))});
    showApp(); await loadRecent(); await checkModel(); navigate();
  } catch (error) { toast(error.message, "error"); }
  finally { button.disabled = false; }
});
$("#composer").addEventListener("submit", sendChat);
$("#chatInput").addEventListener("input", resizeComposer);
$("#chatInput").addEventListener("keydown", event => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); $("#composer").requestSubmit(); } });
$("#stopButton").addEventListener("click", () => state.controller?.abort());
$("#newChatButton").addEventListener("click", newChat);
$("#profileButton").addEventListener("click", () => location.hash = "settings");
$$('[data-prompt]').forEach(button => button.addEventListener("click", () => { $("#chatInput").value = button.dataset.prompt; resizeComposer(); $("#chatInput").focus(); }));
$("#researchForm").addEventListener("submit", runResearch);
$("#projectForm").addEventListener("submit", createProject);
$("#knowledgeForm").addEventListener("submit", createKnowledge);
$("#addKnowledgeButton").addEventListener("click", () => $("#knowledgeDialog").showModal());
$("#knowledgeSearch").addEventListener("input", () => loadKnowledge().catch(() => {}));
$("#knowledgeCategory").addEventListener("change", () => loadKnowledge().catch(() => {}));
$("#historySearch").addEventListener("input", () => loadHistory().catch(() => {}));
$("#archiveFilter").addEventListener("change", () => loadHistory().catch(() => {}));
$("#fileInput").addEventListener("change", event => analyzeFile(event.target.files[0]));
const dropZone = $("#dropZone");
["dragenter", "dragover"].forEach(type => dropZone.addEventListener(type, event => { event.preventDefault(); dropZone.classList.add("dragging"); }));
["dragleave", "drop"].forEach(type => dropZone.addEventListener(type, event => { event.preventDefault(); dropZone.classList.remove("dragging"); }));
dropZone.addEventListener("drop", event => analyzeFile(event.dataTransfer.files[0]));
$("#exportButton").addEventListener("click", async () => { const data = await api("/api/auth/export"); const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], {type: "application/json"})); const link = element("a", {href: url, attrs: {download: "localai-data-export.json"}}); link.click(); URL.revokeObjectURL(url); });
$("#logoutButton").addEventListener("click", async () => { await api("/api/auth/logout", {method: "POST"}); location.hash = ""; showLogin(); });
$("#pullModelForm").addEventListener("submit", async event => { event.preventDefault(); const button = $("button", event.currentTarget); button.disabled = true; try { await api("/api/admin/models/pull", {method: "POST", body: Object.fromEntries(new FormData(event.currentTarget))}); toast("Model installed."); await loadAdmin(); } catch (error) { toast(error.message, "error"); } finally { button.disabled = false; } });
document.addEventListener("click", event => handleDelegatedClick(event).catch(error => toast(error.message, "error")));
window.addEventListener("hashchange", navigate);
boot();
