const state = {
  problems: [],
  currentProblem: null,
  difficulty: "all",
  mode: "explain",
  editor: null,
  draftTimer: null,
  suppressDraft: false,
  selection: {text: "", source: ""},
};

const el = {
  problemList: document.querySelector("#problemList"),
  searchInput: document.querySelector("#searchInput"),
  updateStatus: document.querySelector("#updateStatus"),
  updateBtn: document.querySelector("#updateBtn"),
  difficulty: document.querySelector("#difficulty"),
  problemTitle: document.querySelector("#problemTitle"),
  description: document.querySelector("#description"),
  sourceNote: document.querySelector("#sourceNote"),
  tags: document.querySelector("#tags"),
  schema: document.querySelector("#schema"),
  submissions: document.querySelector("#submissions"),
  solutionBox: document.querySelector("#solutionBox"),
  solutionBtn: document.querySelector("#solutionBtn"),
  sqlEditor: document.querySelector("#sqlEditor"),
  runBtn: document.querySelector("#runBtn"),
  resetBtn: document.querySelector("#resetBtn"),
  saveDraftBtn: document.querySelector("#saveDraftBtn"),
  status: document.querySelector("#status"),
  actualResult: document.querySelector("#actualResult"),
  judgeResult: document.querySelector("#judgeResult"),
  toggleSettingsBtn: document.querySelector("#toggleSettingsBtn"),
  settings: document.querySelector("#settings"),
  baseUrl: document.querySelector("#baseUrl"),
  model: document.querySelector("#model"),
  apiKey: document.querySelector("#apiKey"),
  reloadConfigBtn: document.querySelector("#reloadConfigBtn"),
  configStatus: document.querySelector("#configStatus"),
  aiMessage: document.querySelector("#aiMessage"),
  askBtn: document.querySelector("#askBtn"),
  aiReply: document.querySelector("#aiReply"),
  contextMenu: document.querySelector("#contextMenu"),
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: {"Content-Type": "application/json"},
    ...options,
  });
  const data = await response.json();
  if (!response.ok || data.error) {
    const error = new Error(data.error || `请求失败：${response.status}`);
    error.data = data;
    throw error;
  }
  return data;
}

function difficultyLabel(difficulty) {
  const map = {Easy: "简单", Medium: "中等", Hard: "困难"};
  return map[difficulty] || difficulty;
}

function initEditor() {
  state.editor = CodeMirror.fromTextArea(el.sqlEditor, {
    mode: "text/x-sql",
    theme: "default",
    lineNumbers: true,
    matchBrackets: true,
    indentUnit: 2,
    tabSize: 2,
    lineWrapping: true,
    extraKeys: {
      "Ctrl-Enter": runSql,
      "Cmd-Enter": runSql,
      "Ctrl-S": () => saveDraftNow(),
      "Cmd-S": () => saveDraftNow(),
    },
  });
  state.editor.on("change", () => {
    if (!state.suppressDraft) scheduleDraftSave();
  });
}

function getSql() {
  return state.editor ? state.editor.getValue() : el.sqlEditor.value;
}

function setSql(sql) {
  state.suppressDraft = true;
  if (state.editor) {
    state.editor.setValue(sql || "");
    state.editor.refresh();
  } else {
    el.sqlEditor.value = sql || "";
  }
  window.setTimeout(() => {
    state.suppressDraft = false;
  }, 0);
}

function selectedSql() {
  return state.editor ? state.editor.getSelection() : "";
}

function renderProblemList() {
  const query = el.searchInput.value.trim().toLowerCase();
  const problems = state.problems.filter((problem) => {
    const text = `${problem.title} ${problem.difficulty} ${(problem.tags || []).join(" ")}`.toLowerCase();
    const difficultyOk = state.difficulty === "all" || problem.difficulty === state.difficulty;
    return difficultyOk && text.includes(query);
  });

  el.problemList.innerHTML = problems
    .map((problem) => {
      const active = state.currentProblem?.id === problem.id ? " active" : "";
      const solved = problem.accepted ? " solved" : "";
      const count = problem.submissionCount ? ` · ${problem.submissionCount} 次提交` : "";
      return `
        <button class="problem-item${active}${solved}" data-id="${escapeHtml(problem.id)}">
          <strong>${problem.accepted ? "✓ " : ""}${escapeHtml(problem.title)}</strong>
          <span>${difficultyLabel(problem.difficulty)} · ${(problem.tags || []).join(" / ")}${count}</span>
        </button>
      `;
    })
    .join("");
}

function tableHtml(columns, rows) {
  if (!columns?.length) return "<span class=\"muted\">无列</span>";
  const body = rows
    .map((row) => `<tr>${row.map((cell) => `<td>${cell === null ? "<em>NULL</em>" : escapeHtml(cell)}</td>`).join("")}</tr>`)
    .join("");
  return `
    <table>
      <thead><tr>${columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr></thead>
      <tbody>${body || `<tr><td colspan="${columns.length}">空结果</td></tr>`}</tbody>
    </table>
  `;
}

function renderSchema(problem) {
  el.schema.innerHTML = problem.schema
    .map((table) => {
      const columns = table.columns
        .map((column) => `<span class="column-pill">${escapeHtml(column.name)} <small>${escapeHtml(column.type)}</small></span>`)
        .join("");
      const previewRows = table.rows.map((row) => table.columns.map((column) => row[column.name]));
      return `
        <article class="table-card">
          <h2>${escapeHtml(table.name)}</h2>
          <div class="columns">${columns}</div>
          ${tableHtml(table.columns.map((column) => column.name), previewRows)}
        </article>
      `;
    })
    .join("");
}

function renderProblem(problem) {
  state.currentProblem = problem;
  el.difficulty.textContent = difficultyLabel(problem.difficulty);
  el.problemTitle.textContent = problem.title;
  el.description.textContent = problem.description;
  el.tags.innerHTML = (problem.tags || []).map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("");
  el.sourceNote.textContent = problem.source_note || "";
  el.sourceNote.classList.toggle("hidden", !problem.source_note);
  setSql(problem.starter_sql || "");
  el.actualResult.textContent = "运行后显示结果";
  el.actualResult.classList.add("muted");
  el.judgeResult.textContent = "尚未运行";
  el.judgeResult.classList.add("muted");
  el.solutionBox.textContent = "解析默认隐藏。需要时点击查看完整解法。";
  el.solutionBox.classList.add("muted");
  renderSchema(problem);
  renderProblemList();
  loadSubmissions(problem.id);
  switchTab("description");
}

async function loadProblem(problemId) {
  const problem = await api(`/api/problems/${encodeURIComponent(problemId)}`);
  renderProblem(problem);
}

async function reloadProblems(keepCurrent = true) {
  const currentId = keepCurrent ? state.currentProblem?.id : null;
  state.problems = await api("/api/problems");
  renderProblemList();
  if (currentId && state.problems.some((problem) => problem.id === currentId)) {
    await loadProblem(currentId);
  } else if (state.problems.length) {
    await loadProblem(state.problems[0].id);
  }
}

function switchTab(tabName) {
  document.querySelectorAll(".tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.tab === tabName));
  document.querySelectorAll(".tab-panel").forEach((panel) => panel.classList.remove("active"));
  document.querySelector(`#${tabName}Tab`)?.classList.add("active");
}

function renderJudge(result) {
  const {comparison} = result;
  const title = comparison.accepted ? "Accepted" : "Wrong Answer";
  const className = comparison.accepted ? "accepted" : "failed";
  const details = [
    `列名：${comparison.sameColumns ? "匹配" : "不匹配"}`,
    `行数据：${comparison.sameRows ? "匹配" : "不匹配"}`,
    `输出行数：${comparison.rowCount}`,
    `期望行数：${comparison.expectedRowCount}`,
  ];
  el.judgeResult.classList.remove("muted");
  el.judgeResult.innerHTML = `<p class="${className}">${title}</p>${details.map((item) => `<p>${item}</p>`).join("")}`;
}

async function runSql() {
  if (!state.currentProblem) return;
  el.status.textContent = "运行中...";
  el.runBtn.disabled = true;
  try {
    const result = await api("/api/run", {
      method: "POST",
      body: JSON.stringify({
        problemId: state.currentProblem.id,
        sql: getSql(),
      }),
    });
    el.actualResult.classList.remove("muted");
    el.actualResult.innerHTML = tableHtml(result.actual.columns, result.actual.rows);
    renderJudge(result);
    el.status.textContent = result.comparison.accepted ? "答案通过" : "结果不匹配";
    state.problems = await api("/api/problems");
    renderProblemList();
    await loadSubmissions(state.currentProblem.id);
  } catch (error) {
    el.status.textContent = "运行失败";
    el.actualResult.classList.remove("muted");
    el.actualResult.innerHTML = `<span class="failed">${escapeHtml(error.message)}</span>`;
    await loadSubmissions(state.currentProblem.id);
  } finally {
    el.runBtn.disabled = false;
  }
}

async function saveDraftNow() {
  if (!state.currentProblem) return;
  window.clearTimeout(state.draftTimer);
  await api("/api/draft", {
    method: "POST",
    body: JSON.stringify({problemId: state.currentProblem.id, sql: getSql()}),
  });
  el.status.textContent = "草稿已保存";
}

function scheduleDraftSave() {
  window.clearTimeout(state.draftTimer);
  state.draftTimer = window.setTimeout(() => {
    saveDraftNow().catch(() => {
      el.status.textContent = "草稿保存失败";
    });
  }, 800);
}

async function loadSubmissions(problemId) {
  const items = await api(`/api/submissions?problemId=${encodeURIComponent(problemId)}`);
  if (!items.length) {
    el.submissions.textContent = "暂无提交记录";
    el.submissions.classList.add("muted");
    return;
  }
  el.submissions.classList.remove("muted");
  el.submissions.innerHTML = items
    .slice()
    .reverse()
    .map((item) => {
      const status = item.accepted ? "Accepted" : "Wrong Answer";
      const statusClass = item.accepted ? "accepted" : "failed";
      const rowCount = item.resultSummary ? `${item.resultSummary.rowCount} 行` : "无结果";
      return `
        <article class="submission-item">
          <div><strong class="${statusClass}">${status}</strong><span>${escapeHtml(item.submittedAt)}</span></div>
          <p>${escapeHtml(item.error || rowCount)}</p>
          <pre>${escapeHtml(item.sql)}</pre>
        </article>
      `;
    })
    .join("");
}

async function loadSolution() {
  if (!state.currentProblem) return;
  el.solutionBtn.disabled = true;
  el.solutionBox.textContent = "加载解析中...";
  try {
    const data = await api(`/api/solution?problemId=${encodeURIComponent(state.currentProblem.id)}`);
    el.solutionBox.classList.remove("muted");
    el.solutionBox.innerHTML = `
      <p>${escapeHtml(data.explanation)}</p>
      <pre>${escapeHtml(data.solution)}</pre>
    `;
  } catch (error) {
    el.solutionBox.innerHTML = `<span class="failed">${escapeHtml(error.message)}</span>`;
  } finally {
    el.solutionBtn.disabled = false;
  }
}

async function loadProvider() {
  const config = await api("/api/ai-config");
  el.baseUrl.value = config.baseUrl || "https://api.openai.com/v1";
  el.model.value = config.model || "";
  el.apiKey.value = config.apiKey || "";
  el.configStatus.textContent = "已从 data/ai_config.json 读取";
}

function currentProvider() {
  return {
    baseUrl: el.baseUrl.value.trim(),
    model: el.model.value.trim(),
    apiKey: el.apiKey.value.trim(),
  };
}

async function askAssistant(options = {}) {
  if (!state.currentProblem) return;
  const mode = options.mode || state.mode;
  el.askBtn.disabled = true;
  el.aiReply.textContent = "思考中...";
  el.aiReply.classList.add("muted");
  try {
    const data = await api("/api/ai", {
      method: "POST",
      body: JSON.stringify({
        problemId: state.currentProblem.id,
        sql: getSql(),
        mode,
        allowSolution: mode === "solution",
        selectedText: options.selectedText || "",
        selectionSource: options.selectionSource || "",
        message: options.message ?? el.aiMessage.value,
      }),
    });
    el.aiReply.classList.remove("muted");
    el.aiReply.textContent = data.reply;
  } catch (error) {
    el.aiReply.classList.remove("muted");
    el.aiReply.innerHTML = `<span class="failed">${escapeHtml(error.message)}</span>`;
  } finally {
    el.askBtn.disabled = false;
  }
}

function renderUpdateStatus(status) {
  if (!status?.lastChecked) {
    el.updateStatus.textContent = "尚未检查";
    return;
  }
  const addedText = status.added ? `新增 ${status.added} 道` : "今日已检查";
  el.updateStatus.textContent = `${status.lastChecked} · ${addedText}`;
}

async function loadUpdateStatus() {
  try {
    renderUpdateStatus(await api("/api/update-status"));
  } catch (error) {
    el.updateStatus.textContent = "状态不可用";
  }
}

async function updateProblems() {
  el.updateBtn.disabled = true;
  el.updateStatus.textContent = "更新中...";
  try {
    const result = await api("/api/update-problems", {
      method: "POST",
      body: JSON.stringify({force: true}),
    });
    el.updateStatus.textContent = result.message;
    await reloadProblems(true);
    await loadUpdateStatus();
  } catch (error) {
    el.updateStatus.textContent = error.message;
  } finally {
    el.updateBtn.disabled = false;
  }
}

function getPageSelection(event) {
  const editorText = selectedSql();
  if (editorText.trim()) {
    return {text: editorText, source: "SQL 编辑器"};
  }
  const selection = window.getSelection();
  const text = selection ? selection.toString() : "";
  const source = event.target.closest(".problem-pane") ? "题目区域"
    : event.target.closest(".editor-pane") ? "编辑结果区域"
    : event.target.closest(".assistant-pane") ? "AI 助手区域"
    : "页面";
  return {text, source};
}

function showContextMenu(event) {
  const selection = getPageSelection(event);
  if (!selection.text.trim()) {
    hideContextMenu();
    return;
  }
  event.preventDefault();
  state.selection = selection;
  el.contextMenu.style.left = `${Math.min(event.clientX, window.innerWidth - 240)}px`;
  el.contextMenu.style.top = `${Math.min(event.clientY, window.innerHeight - 180)}px`;
  el.contextMenu.classList.remove("hidden");
}

function hideContextMenu() {
  el.contextMenu.classList.add("hidden");
}

el.problemList.addEventListener("click", (event) => {
  const button = event.target.closest("[data-id]");
  if (button) loadProblem(button.dataset.id);
});

el.searchInput.addEventListener("input", renderProblemList);
document.querySelectorAll(".difficulty-filter").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".difficulty-filter").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    state.difficulty = button.dataset.difficulty;
    renderProblemList();
  });
});

document.querySelectorAll(".tab").forEach((button) => {
  button.addEventListener("click", () => switchTab(button.dataset.tab));
});

el.updateBtn.addEventListener("click", updateProblems);
el.runBtn.addEventListener("click", runSql);
el.saveDraftBtn.addEventListener("click", () => saveDraftNow().catch((error) => {
  el.status.textContent = error.message;
}));
el.resetBtn.addEventListener("click", () => {
  if (state.currentProblem) setSql(state.currentProblem.template_sql || state.currentProblem.starter_sql || "");
});
el.solutionBtn.addEventListener("click", loadSolution);

el.toggleSettingsBtn.addEventListener("click", () => {
  const hidden = el.settings.classList.toggle("hidden");
  el.toggleSettingsBtn.setAttribute("aria-expanded", String(!hidden));
  if (!hidden) {
    loadProvider().catch((error) => {
      el.configStatus.textContent = error.message;
    });
  }
});

el.settings.addEventListener("submit", async (event) => {
  event.preventDefault();
  el.configStatus.textContent = "保存中...";
  try {
    await api("/api/ai-config", {
      method: "POST",
      body: JSON.stringify(currentProvider()),
    });
    el.configStatus.textContent = "已写入 data/ai_config.json";
  } catch (error) {
    el.configStatus.textContent = error.message;
  }
});

el.reloadConfigBtn.addEventListener("click", () => {
  el.configStatus.textContent = "读取中...";
  loadProvider().catch((error) => {
    el.configStatus.textContent = error.message;
  });
});

document.querySelectorAll(".ai-action").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".ai-action").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    state.mode = button.dataset.mode;
    askAssistant({mode: state.mode});
  });
});

el.askBtn.addEventListener("click", () => askAssistant());
document.addEventListener("contextmenu", showContextMenu);
document.addEventListener("click", (event) => {
  if (!event.target.closest("#contextMenu")) hideContextMenu();
});
el.contextMenu.addEventListener("click", (event) => {
  const button = event.target.closest("[data-context-mode]");
  if (!button) return;
  const message = button.dataset.contextMode === "selection-ask" ? el.aiMessage.value : "";
  askAssistant({
    mode: button.dataset.contextMode,
    selectedText: state.selection.text,
    selectionSource: state.selection.source,
    message,
  });
  hideContextMenu();
});

async function start() {
  initEditor();
  await loadProvider();
  await reloadProblems(false);
  await loadUpdateStatus();
}

start().catch((error) => {
  el.status.textContent = error.message;
});
