const apiPrefix = "/api/v1";
const tokenStorageKey = "chatrobot_access_token";

const state = {
  accessToken: window.localStorage.getItem(tokenStorageKey),
  currentUser: null,
  collections: [],
  datasets: [],
  reports: [],
  selectedCollectionId: "",
  selectedDatasetPath: "",
  selectedReportId: "",
  activeReport: null,
  activeTask: null,
  running: false,
  sessionMessage: "",
};

const elements = {
  evalCurrentUserCard: document.getElementById("evalCurrentUserCard"),
  evalHeroStats: document.getElementById("evalHeroStats"),
  evalCurrentUsername: document.getElementById("evalCurrentUsername"),
  evalCurrentUserEmail: document.getElementById("evalCurrentUserEmail"),
  evalDatasetCount: document.getElementById("evalDatasetCount"),
  evalReportCount: document.getElementById("evalReportCount"),
  evalLatestPrimaryScore: document.getElementById("evalLatestPrimaryScore"),
  evalLatestAnswerScore: document.getElementById("evalLatestAnswerScore"),
  evalRefreshButton: document.getElementById("evalRefreshButton"),
  evalSessionNotice: document.getElementById("evalSessionNotice"),
  evalLoginGate: document.getElementById("evalLoginGate"),
  evalDashboard: document.getElementById("evalDashboard"),
  evalRunForm: document.getElementById("evalRunForm"),
  evalCollectionSelect: document.getElementById("evalCollectionSelect"),
  evalCollectionHint: document.getElementById("evalCollectionHint"),
  evalDatasetSelect: document.getElementById("evalDatasetSelect"),
  evalTopKInput: document.getElementById("evalTopKInput"),
  evalHybridSelect: document.getElementById("evalHybridSelect"),
  evalRerankSelect: document.getElementById("evalRerankSelect"),
  evalAnswerModeSelect: document.getElementById("evalAnswerModeSelect"),
  evalJudgeModeSelect: document.getElementById("evalJudgeModeSelect"),
  evalPersistCheckbox: document.getElementById("evalPersistCheckbox"),
  evalRunButton: document.getElementById("evalRunButton"),
  evalRunProgress: document.getElementById("evalRunProgress"),
  evalRunProgressLabel: document.getElementById("evalRunProgressLabel"),
  evalRunProgressStatus: document.getElementById("evalRunProgressStatus"),
  evalRunProgressBar: document.getElementById("evalRunProgressBar"),
  evalReportsEmptyState: document.getElementById("evalReportsEmptyState"),
  evalReportList: document.getElementById("evalReportList"),
  evalDetailTitle: document.getElementById("evalDetailTitle"),
  evalDetailMeta: document.getElementById("evalDetailMeta"),
  evalDetailEmptyState: document.getElementById("evalDetailEmptyState"),
  evalDetailBody: document.getElementById("evalDetailBody"),
  evalSummaryGrid: document.getElementById("evalSummaryGrid"),
  evalCaseResults: document.getElementById("evalCaseResults"),
  evalToast: document.getElementById("evalToast"),
};

function showToast(message, isError = false) {
  elements.evalToast.textContent = message;
  elements.evalToast.style.background = isError ? "rgba(143, 50, 23, 0.94)" : "rgba(31, 27, 22, 0.9)";
  elements.evalToast.classList.remove("hidden");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    elements.evalToast.classList.add("hidden");
  }, 2600);
}

function setSessionNotice(message = "") {
  state.sessionMessage = message;
  if (!message) {
    elements.evalSessionNotice.classList.add("hidden");
    elements.evalSessionNotice.textContent = "";
    return;
  }
  elements.evalSessionNotice.textContent = message;
  elements.evalSessionNotice.classList.remove("hidden");
}

async function parseResponsePayload(response) {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  return response.text();
}

/**
 * Extract a user-facing error message from any API failure shape.
 * FastAPI returns {"detail": [...]} for 422 validation; backend exceptions
 * use {"code": "...", "message": "..."}; network failures have neither.
 */
function extractErrorMessage(err, fallback = "请求失败,请稍后重试。") {
  if (err && typeof err.message === "string" && err.message) {
    return err.message;
  }
  if (err && Array.isArray(err.detail) && err.detail.length > 0) {
    return err.detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
  }
  if (err && typeof err.detail === "string" && err.detail) {
    return err.detail;
  }
  return fallback;
}

async function assertOkResponse(response) {
  if (response.ok) {
    return response;
  }
  const payload = await parseResponsePayload(response);
  const message = extractErrorMessage(payload, "请求失败");
  if (response.status === 401) {
    state.accessToken = null;
    state.currentUser = null;
    window.localStorage.removeItem(tokenStorageKey);
    renderAuthState();
  }
  throw new Error(message);
}

async function request(url, options = {}) {
  const headers = new Headers(options.headers || {});
  if (state.accessToken && options.includeAuth !== false) {
    headers.set("Authorization", `Bearer ${state.accessToken}`);
  }
  const response = await fetch(url, { ...options, headers });
  await assertOkResponse(response);
  return parseResponsePayload(response);
}

function formatDateTime(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatScore(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  return Number(value).toFixed(3);
}

function getPrimaryMetricDisplay(target) {
  const metrics = target?.primary_metrics;
  const level = target?.primary_label_level || (metrics ? "legacy" : "unavailable");
  if (level === "source-only") {
    return {
      level,
      measurable: false,
      value: "—",
      note: "仅能测来源命中",
    };
  }
  if (level === "unavailable" || !metrics) {
    return {
      level: "unavailable",
      measurable: false,
      value: "—",
      note: "主检索指标不可测",
    };
  }
  const labels = {
    evidence: "evidence",
    chunk: "chunk",
    document: "document",
    mixed: "mixed",
    legacy: "legacy",
  };
  return {
    level,
    measurable: true,
    value: formatScore(metrics.recall_at_k),
    note: `${labels[level] || level} labels`,
  };
}

function renderAuthState() {
  const authenticated = Boolean(state.accessToken && state.currentUser);
  document.body.classList.toggle("is-authenticated", authenticated);
  elements.evalLoginGate.classList.toggle("hidden", authenticated);
  elements.evalDashboard.classList.toggle("hidden", !authenticated);
  elements.evalCurrentUserCard.classList.toggle("hidden", !authenticated);
  elements.evalHeroStats.classList.toggle("hidden", !authenticated);
  elements.evalRefreshButton.classList.toggle("hidden", !authenticated);

  if (authenticated) {
    elements.evalCurrentUsername.textContent = state.currentUser.username;
    elements.evalCurrentUserEmail.textContent = state.currentUser.email;
  } else {
    elements.evalCurrentUsername.textContent = "-";
    elements.evalCurrentUserEmail.textContent = "-";
    setSessionNotice("登录后可查看和运行 RAG 评估。");
  }
}

function renderSummaryHeader() {
  elements.evalDatasetCount.textContent = String(state.datasets.length);
  elements.evalReportCount.textContent = String(state.reports.length);
  const latest = state.reports[0];
  const primaryDisplay = getPrimaryMetricDisplay(latest?.summary);
  elements.evalLatestPrimaryScore.textContent = latest ? primaryDisplay.value : "-";
  elements.evalLatestPrimaryScore.title = latest ? primaryDisplay.note : "暂无报告";
  elements.evalLatestAnswerScore.textContent = latest ? formatScore(latest.summary?.answer_metrics?.overall_answer_score) : "-";
}

function updateCollectionSelection() {
  const selectedCollection = state.collections.find((item) => item.id === state.selectedCollectionId);
  if (selectedCollection) {
    elements.evalCollectionHint.textContent = `已选择“${selectedCollection.name}”；运行时自动提交对应的 collection.id。`;
  } else if (state.collections.length) {
    elements.evalCollectionHint.textContent = `当前用户共有 ${state.collections.length} 个知识库，请选择用于本次评测的库。`;
  } else {
    elements.evalCollectionHint.textContent = "当前账号暂无知识库，请先返回工作台创建知识库并完成文档索引。";
  }
  updateRunButton();
}

function renderCollectionOptions() {
  if (state.selectedCollectionId && !state.collections.some((item) => item.id === state.selectedCollectionId)) {
    state.selectedCollectionId = "";
  }

  elements.evalCollectionSelect.innerHTML = "";
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = state.collections.length ? "请选择评测知识库" : "当前账号暂无知识库";
  placeholder.disabled = Boolean(state.collections.length);
  elements.evalCollectionSelect.appendChild(placeholder);

  state.collections.forEach((collection) => {
    const option = document.createElement("option");
    option.value = collection.id;
    option.textContent = `${collection.name} · ${String(collection.vector_backend || "unknown").toUpperCase()}`;
    elements.evalCollectionSelect.appendChild(option);
  });

  elements.evalCollectionSelect.value = state.selectedCollectionId;
  updateCollectionSelection();
}

function renderDatasetOptions() {
  elements.evalDatasetSelect.innerHTML = "";
  state.datasets.forEach((dataset) => {
    const option = document.createElement("option");
    option.value = dataset.dataset_path;
    option.textContent = `${dataset.dataset_name} (${dataset.case_count})`;
    elements.evalDatasetSelect.appendChild(option);
  });

  if (state.selectedDatasetPath && !state.datasets.some((item) => item.dataset_path === state.selectedDatasetPath)) {
    state.selectedDatasetPath = "";
  }
  if (!state.selectedDatasetPath && state.datasets.length) {
    state.selectedDatasetPath = state.datasets[0].dataset_path;
  }
  elements.evalDatasetSelect.value = state.selectedDatasetPath || "";
}

function renderReportList() {
  elements.evalReportList.innerHTML = "";
  elements.evalReportsEmptyState.style.display = state.reports.length ? "none" : "block";

  state.reports.forEach((report) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "conversation-item eval-report-card";
    if (report.report_id === state.selectedReportId) {
      button.classList.add("selected");
    }

    const title = document.createElement("p");
    title.className = "conversation-title";
    title.textContent = report.dataset_name;

    const meta = document.createElement("div");
    meta.className = "document-meta";
    meta.textContent = `${formatDateTime(report.created_at)} | top_k=${report.summary.top_k}`;

    const scores = document.createElement("div");
    scores.className = "eval-inline-metrics";
    const primaryDisplay = getPrimaryMetricDisplay(report.summary);
    scores.textContent = `主分 ${primaryDisplay.value}（${primaryDisplay.note}） | 答案 ${formatScore(report.summary.answer_metrics?.overall_answer_score)} | Judge ${formatScore(report.summary.llm_judge_metrics?.overall_score)}`;

    button.appendChild(title);
    button.appendChild(meta);
    button.appendChild(scores);
    button.addEventListener("click", () => {
      void loadReportDetail(report.report_id);
    });
    elements.evalReportList.appendChild(button);
  });
}

function buildMetricCard(label, value, meta = "") {
  const article = document.createElement("article");
  article.className = "hero-stat-card eval-metric-card";

  const labelNode = document.createElement("span");
  labelNode.className = "hero-stat-label";
  labelNode.textContent = label;

  const valueNode = document.createElement("strong");
  valueNode.className = "hero-stat-value";
  valueNode.textContent = value;

  article.appendChild(labelNode);
  article.appendChild(valueNode);

  if (meta) {
    const metaNode = document.createElement("span");
    metaNode.className = "document-meta";
    metaNode.textContent = meta;
    article.appendChild(metaNode);
  }
  return article;
}

function renderActiveReport() {
  const storedReport = state.activeReport;
  if (!storedReport) {
    elements.evalDetailEmptyState.classList.remove("hidden");
    elements.evalDetailBody.classList.add("hidden");
    elements.evalDetailTitle.textContent = "报告详情";
    elements.evalDetailMeta.textContent = "选择左侧报告后在这里查看明细。";
    return;
  }

  const report = storedReport.report;
  const summary = report.summary;
  elements.evalDetailEmptyState.classList.add("hidden");
  elements.evalDetailBody.classList.remove("hidden");
  elements.evalDetailTitle.textContent = report.dataset_name;
  elements.evalDetailMeta.textContent = `${formatDateTime(storedReport.created_at)} | ${storedReport.dataset_path} | answer=${storedReport.answer_mode} | judge=${storedReport.llm_judge_mode}`;

  elements.evalSummaryGrid.innerHTML = "";
  const primaryDisplay = getPrimaryMetricDisplay(summary);
  if (primaryDisplay.measurable) {
    elements.evalSummaryGrid.appendChild(buildMetricCard("主 Recall@K", primaryDisplay.value, `${primaryDisplay.note} | cases=${summary.primary_metrics.case_count}`));
    elements.evalSummaryGrid.appendChild(buildMetricCard("主 MRR@K", formatScore(summary.primary_metrics.mrr_at_k), `top_k=${summary.top_k}`));
  } else {
    elements.evalSummaryGrid.appendChild(buildMetricCard("主检索指标", primaryDisplay.value, primaryDisplay.note));
  }
  elements.evalSummaryGrid.appendChild(buildMetricCard("Source", formatScore(summary.source_metrics?.source_match), "source match"));
  elements.evalSummaryGrid.appendChild(buildMetricCard("Latency", summary.latency_metrics?.avg_total_ms ? `${Number(summary.latency_metrics.avg_total_ms).toFixed(0)} ms` : "-", "avg total"));
  elements.evalSummaryGrid.appendChild(buildMetricCard("Tokens", summary.token_usage?.avg_total_tokens ? Number(summary.token_usage.avg_total_tokens).toFixed(0) : "-", "avg total"));
  elements.evalSummaryGrid.appendChild(buildMetricCard("Answer", formatScore(summary.answer_metrics?.overall_answer_score), "heuristic"));
  elements.evalSummaryGrid.appendChild(buildMetricCard("Grounded", formatScore(summary.answer_metrics?.groundedness_score), "heuristic"));
  elements.evalSummaryGrid.appendChild(buildMetricCard("Judge", formatScore(summary.llm_judge_metrics?.overall_score), "llm judge"));
  elements.evalSummaryGrid.appendChild(buildMetricCard("Judge Grounded", formatScore(summary.llm_judge_metrics?.groundedness_score), "llm judge"));

  elements.evalCaseResults.innerHTML = "";
  report.case_results.forEach((item) => {
    const article = document.createElement("article");
    article.className = "chunk-card eval-case-card";

    const title = document.createElement("p");
    title.className = "document-name";
    title.textContent = `${item.case_id} | ${item.query}`;

    const meta = document.createElement("div");
    meta.className = "document-meta";
    const itemPrimaryDisplay = getPrimaryMetricDisplay(item);
    const retrievalMetric = itemPrimaryDisplay.measurable
      ? `retrieval=${itemPrimaryDisplay.value}`
      : `retrieval=${itemPrimaryDisplay.value}（${itemPrimaryDisplay.note}）`;
    meta.textContent = `primary=${itemPrimaryDisplay.level} | ${retrievalMetric} | source=${formatScore(item.source_metrics?.source_match)} | latency=${item.latency_metrics?.total_ms || "-"}ms | answer=${formatScore(item.answer_metrics?.overall_answer_score)} | judge=${formatScore(item.llm_judge_metrics?.overall_score)}`;

    article.appendChild(title);
    article.appendChild(meta);

    if (item.answer) {
      const answer = document.createElement("p");
      answer.className = "chunk-card-body";
      answer.textContent = item.answer;
      article.appendChild(answer);
    }

    if (item.answer_metrics?.unsupported_statements?.length) {
      const unsupported = document.createElement("div");
      unsupported.className = "detail-alert";
      unsupported.textContent = `Unsupported: ${item.answer_metrics.unsupported_statements.join(" | ")}`;
      article.appendChild(unsupported);
    }

    if (item.llm_judge_metrics) {
      const judge = document.createElement("div");
      judge.className = "source-item";
      judge.textContent = `Judge strengths: ${item.llm_judge_metrics.strengths.join(" / ") || "-"} | weaknesses: ${item.llm_judge_metrics.weaknesses.join(" / ") || "-"} | rationale: ${item.llm_judge_metrics.rationale || "-"}`;
      article.appendChild(judge);
    }

    if (item.notes?.length) {
      const notes = document.createElement("div");
      notes.className = "source-item";
      notes.textContent = `Notes: ${item.notes.join(" | ")}`;
      article.appendChild(notes);
    }

    elements.evalCaseResults.appendChild(article);
  });
}

function updateRunButton() {
  elements.evalRunButton.disabled = state.running || !state.selectedCollectionId || !state.selectedDatasetPath;
  elements.evalRunButton.textContent = state.running ? "后台评估中..." : "运行评估";
  elements.evalCollectionSelect.disabled = state.running || !state.collections.length;
}

function renderRunProgress(task) {
  if (!task) {
    elements.evalRunProgress.classList.add("hidden");
    return;
  }

  task = {
    ...task,
    total_cases: task.total_cases || state.activeTask?.total_cases || 0,
  };
  state.activeTask = task;
  elements.evalRunProgress.classList.remove("hidden");
  elements.evalRunProgressLabel.textContent = `已完成 ${task.completed_cases}/${task.total_cases}`;
  elements.evalRunProgressBar.max = Math.max(task.total_cases, 1);
  elements.evalRunProgressBar.value = Math.min(task.completed_cases, task.total_cases || 0);

  const statusMessages = {
    queued: "任务已提交，等待 Worker 处理",
    running: "后台评估中，可继续停留在当前页面",
    completed: "评估已完成，报告正在刷新",
    failed: `评估失败：${task.error || "请检查 Worker 日志后重试"}`,
  };
  elements.evalRunProgressStatus.textContent = statusMessages[task.status] || "正在查询任务状态";
}

function wait(milliseconds) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

async function pollEvaluationTask(taskId) {
  while (state.running && state.activeTask?.task_id === taskId) {
    await wait(1200);
    const task = await request(`${apiPrefix}/evaluations/rag/runs/${encodeURIComponent(taskId)}`);
    renderRunProgress(task);
    if (task.status === "completed") {
      return task;
    }
    if (task.status === "failed") {
      throw new Error(task.error || "后台评估失败，请检查 Worker 日志后重试。");
    }
  }
  throw new Error("评估进度查询已停止。");
}

async function loadCurrentUser() {
  state.currentUser = await request(`${apiPrefix}/auth/me`);
  renderAuthState();
}

async function loadCollections() {
  elements.evalCollectionSelect.disabled = true;
  elements.evalCollectionHint.textContent = "正在加载当前用户的知识库...";
  try {
    state.collections = await request(`${apiPrefix}/collections`);
    renderCollectionOptions();
  } catch (error) {
    state.collections = [];
    state.selectedCollectionId = "";
    elements.evalCollectionSelect.innerHTML = '<option value="">知识库加载失败</option>';
    elements.evalCollectionHint.textContent = "知识库加载失败，请刷新看板后重试。";
    updateRunButton();
    throw error;
  }
}

async function loadDatasets() {
  state.datasets = await request(`${apiPrefix}/evaluations/rag/datasets`);
  renderDatasetOptions();
  renderSummaryHeader();
}

async function loadReports() {
  state.reports = await request(`${apiPrefix}/evaluations/rag/reports`);
  if (state.selectedReportId && !state.reports.some((item) => item.report_id === state.selectedReportId)) {
    state.selectedReportId = "";
    state.activeReport = null;
  }
  if (!state.selectedReportId && state.reports.length) {
    state.selectedReportId = state.reports[0].report_id;
  }
  renderReportList();
  renderSummaryHeader();
}

async function loadReportDetail(reportId) {
  state.selectedReportId = reportId;
  renderReportList();
  state.activeReport = await request(`${apiPrefix}/evaluations/rag/reports/${encodeURIComponent(reportId)}`);
  renderActiveReport();
}

function parseOptionalBoolean(value) {
  if (value === "true") {
    return true;
  }
  if (value === "false") {
    return false;
  }
  return null;
}

async function runEvaluation() {
  state.running = true;
  updateRunButton();
  try {
    const payload = {
      dataset_path: state.selectedDatasetPath,
      collection_id: state.selectedCollectionId,
      top_k: elements.evalTopKInput.value ? Number(elements.evalTopKInput.value) : null,
      use_hybrid_search: parseOptionalBoolean(elements.evalHybridSelect.value),
      use_rerank: parseOptionalBoolean(elements.evalRerankSelect.value),
      answer_mode: elements.evalAnswerModeSelect.value,
      llm_judge_mode: elements.evalJudgeModeSelect.value,
      persist: elements.evalPersistCheckbox.checked,
    };

    const acceptedTask = await request(`${apiPrefix}/evaluations/rag/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    renderRunProgress(acceptedTask);
    const completedTask = await pollEvaluationTask(acceptedTask.task_id);

    await loadReports();
    if (completedTask.stored_report) {
      state.activeReport = completedTask.stored_report;
      state.selectedReportId = completedTask.report_id || "";
      renderReportList();
      renderActiveReport();
    } else if (completedTask.report_id) {
      await loadReportDetail(completedTask.report_id);
    }
    showToast("评估已完成，报告已更新。");
  } catch (error) {
    showToast(error.message, true);
  } finally {
    state.running = false;
    updateRunButton();
  }
}

async function refreshBoard() {
  await loadCollections();
  await loadDatasets();
  await loadReports();
  if (state.selectedReportId) {
    await loadReportDetail(state.selectedReportId);
  } else {
    renderActiveReport();
  }
}

elements.evalCollectionSelect.addEventListener("change", (event) => {
  state.selectedCollectionId = event.target.value;
  updateCollectionSelection();
});

elements.evalDatasetSelect.addEventListener("change", (event) => {
  state.selectedDatasetPath = event.target.value;
  updateRunButton();
});

elements.evalRunForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await runEvaluation();
});

elements.evalRefreshButton.addEventListener("click", async () => {
  try {
    await refreshBoard();
    showToast("评估看板已刷新。");
  } catch (error) {
    showToast(error.message, true);
  }
});

async function bootstrap() {
  renderAuthState();
  updateRunButton();
  renderActiveReport();

  if (!state.accessToken) {
    return;
  }

  try {
    await loadCurrentUser();
    await refreshBoard();
    setSessionNotice("");
  } catch (error) {
    setSessionNotice(error.message || "评估看板加载失败。");
    showToast(error.message, true);
  }
}

bootstrap();
