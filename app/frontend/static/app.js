const apiPrefix = "/api/v1";
const tokenStorageKey = "chatrobot_access_token";
const documentPollIntervalMs = 3000;
const documentPollingStatuses = new Set(["uploaded", "queued", "processing"]);
const uploadQueueActiveStatuses = new Set(["waiting", "uploading", "uploaded", "queued", "processing"]);
const registeredNoticeParam = "registered";

const state = {
  accessToken: window.localStorage.getItem(tokenStorageKey),
  currentUser: null,
  collections: [],
  conversations: [],
  selectedCollectionId: "",
  documents: [],
  conversationId: null,
  sessionMessage: "",
  chatStreaming: false,
  currentStreamController: null,
  uploadQueue: [],
  uploadQueueSeed: 0,
  uploadProcessing: false,
  selectedDocumentId: null,
  selectedDocumentDetail: null,
  documentDetailLoading: false,
  documentDetailErrorMessage: "",
  documentPollTimer: null,
  documentPollInFlight: false,
  busyDocumentIds: new Set(),
};

const elements = {
  authPanel: document.getElementById("authPanel"),
  dashboard: document.getElementById("dashboard"),
  sessionNotice: document.getElementById("sessionNotice"),
  currentUserCard: document.getElementById("currentUserCard"),
  currentUsername: document.getElementById("currentUsername"),
  currentUserEmail: document.getElementById("currentUserEmail"),
  workspaceCollectionSummary: document.getElementById("workspaceCollectionSummary"),
  workspaceDocumentSummary: document.getElementById("workspaceDocumentSummary"),
  workspacePendingSummary: document.getElementById("workspacePendingSummary"),
  workspaceConversationSummary: document.getElementById("workspaceConversationSummary"),
  chatCollectionBadge: document.getElementById("chatCollectionBadge"),
  loginForm: document.getElementById("loginForm"),
  loginIdentifierInput: document.getElementById("loginIdentifierInput"),
  loginPasswordInput: document.getElementById("loginPasswordInput"),
  logoutButton: document.getElementById("logoutButton"),
  documentPollingStatus: document.getElementById("documentPollingStatus"),
  collectionSelect: document.getElementById("collectionSelect"),
  collectionForm: document.getElementById("collectionForm"),
  collectionNameInput: document.getElementById("collectionNameInput"),
  collectionDescriptionInput: document.getElementById("collectionDescriptionInput"),
  uploadForm: document.getElementById("uploadForm"),
  uploadSubmitButton: document.querySelector("#uploadForm button[type='submit']"),
  fileInput: document.getElementById("fileInput"),
  uploadQueue: document.getElementById("uploadQueue"),
  uploadQueueEmptyState: document.getElementById("uploadQueueEmptyState"),
  documentsList: document.getElementById("documentsList"),
  documentsEmptyState: document.getElementById("documentsEmptyState"),
  documentDetailPanel: document.getElementById("documentDetailPanel"),
  documentDetailTitle: document.getElementById("documentDetailTitle"),
  documentChunkPreviewSummary: document.getElementById("documentChunkPreviewSummary"),
  documentDetailStatus: document.getElementById("documentDetailStatus"),
  documentDetailMeta: document.getElementById("documentDetailMeta"),
  documentDetailError: document.getElementById("documentDetailError"),
  documentChunkPreview: document.getElementById("documentChunkPreview"),
  documentChunkPreviewEmptyState: document.getElementById("documentChunkPreviewEmptyState"),
  closeDocumentDetailButton: document.getElementById("closeDocumentDetailButton"),
  conversationList: document.getElementById("conversationList"),
  conversationListEmptyState: document.getElementById("conversationListEmptyState"),
  chatFeed: document.getElementById("chatFeed"),
  chatForm: document.getElementById("chatForm"),
  chatInput: document.getElementById("chatInput"),
  chatSubmitButton: document.querySelector("#chatForm button[type='submit']"),
  stopChatButton: document.getElementById("stopChatButton"),
  toast: document.getElementById("toast"),
  refreshAllButton: document.getElementById("refreshAllButton"),
  refreshDocumentsButton: document.getElementById("refreshDocumentsButton"),
  resetConversationButton: document.getElementById("resetConversationButton"),
};

function showToast(message, isError = false) {
  elements.toast.textContent = message;
  elements.toast.style.background = isError ? "rgba(143, 50, 23, 0.94)" : "rgba(31, 27, 22, 0.9)";
  elements.toast.classList.remove("hidden");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    elements.toast.classList.add("hidden");
  }, 2600);
}

function formatBytes(value) {
  const bytes = Number(value || 0);
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
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

function getCollectionById(collectionId) {
  return state.collections.find((collection) => collection.id === collectionId) || null;
}

function getCollectionName(collectionId) {
  return getCollectionById(collectionId)?.name || "未命名知识库";
}

function isDocumentPending(status) {
  return documentPollingStatuses.has(status);
}

function isUploadQueueItemActive(item) {
  return uploadQueueActiveStatuses.has(item.status);
}

function formatStatusLabel(status) {
  const labelMap = {
    waiting: "等待上传",
    uploading: "上传中",
    uploaded: "已上传",
    queued: "排队中",
    processing: "处理中",
    indexed: "已完成",
    failed: "失败",
    deleted: "已删除",
  };
  return labelMap[status] || status;
}

function badgeClass(status) {
  return `status-badge status-${String(status || "unknown").replace(/[^a-z0-9_-]/gi, "-").toLowerCase()}`;
}

function buildDocumentStatusCopy(documentItem) {
  const status = documentItem.status;
  if (status === "uploaded") {
    return "文件已上传，等待入库任务排队。";
  }
  if (status === "queued") {
    return "已进入入库队列，等待 Worker 处理。";
  }
  if (status === "processing") {
    return "正在切分、向量化并写入向量库。";
  }
  if (status === "indexed") {
    return `入库完成，共 ${documentItem.chunk_count} 个分块。`;
  }
  if (status === "failed") {
    return `入库失败：${documentItem.error_message || "请稍后重试。"} `;
  }
  if (status === "deleted") {
    return "文档已删除。";
  }
  return "状态已更新。";
}

function formatDocumentMeta(documentItem) {
  return `${documentItem.file_type.toUpperCase()} · ${formatBytes(documentItem.file_size)} · ${documentItem.chunk_count} chunks`;
}

function renderSessionNotice() {
  if (!state.sessionMessage) {
    elements.sessionNotice.classList.add("hidden");
    elements.sessionNotice.textContent = "";
    return;
  }
  elements.sessionNotice.textContent = state.sessionMessage;
  elements.sessionNotice.classList.remove("hidden");
}

function setSessionNotice(message) {
  state.sessionMessage = message;
  renderSessionNotice();
}

function clearSessionNotice() {
  state.sessionMessage = "";
  renderSessionNotice();
}

function renderWorkspaceSummary() {
  const selectedCollectionName = state.selectedCollectionId
    ? getCollectionName(state.selectedCollectionId)
    : "未选择";
  const pendingDocuments = state.documents.filter((documentItem) => isDocumentPending(documentItem.status)).length;

  elements.workspaceCollectionSummary.textContent = selectedCollectionName;
  elements.workspaceDocumentSummary.textContent = `${state.documents.length} / ${state.collections.length}`;
  elements.workspacePendingSummary.textContent = String(pendingDocuments);
  elements.workspaceConversationSummary.textContent = String(state.conversations.length);
  elements.chatCollectionBadge.textContent = state.selectedCollectionId
    ? `${selectedCollectionName} · ${state.documents.length} 份文档`
    : "未选择知识库";
}

function getDocumentPollingSnapshot() {
  const hasPendingDocuments = state.documents.some((documentItem) => isDocumentPending(documentItem.status));
  const hasActiveUploads = state.uploadProcessing || state.uploadQueue.some((item) => isUploadQueueItemActive(item));
  return {
    hasPendingDocuments,
    hasActiveUploads,
    shouldPoll: Boolean(state.accessToken && state.selectedCollectionId && (hasPendingDocuments || hasActiveUploads)),
  };
}

function readInitialAuthNotice() {
  const url = new URL(window.location.href);
  if (url.searchParams.get(registeredNoticeParam) !== "1") {
    return "";
  }
  url.searchParams.delete(registeredNoticeParam);
  window.history.replaceState({}, document.title, `${url.pathname}${url.search}${url.hash}`);
  return "注册成功，请使用刚刚创建的账号登录。";
}

function stopDocumentPolling() {
  if (state.documentPollTimer) {
    window.clearInterval(state.documentPollTimer);
    state.documentPollTimer = null;
  }
  renderDocumentPollingState();
}

function shouldPollDocuments() {
  return getDocumentPollingSnapshot().shouldPoll;
}

function renderDocumentPollingState() {
  if (!elements.documentPollingStatus) {
    return;
  }

  if (!state.accessToken) {
    elements.documentPollingStatus.textContent = "登录后可自动刷新文档状态";
    return;
  }

  if (!state.selectedCollectionId) {
    elements.documentPollingStatus.textContent = "选择知识库后自动刷新";
    return;
  }

  const snapshot = getDocumentPollingSnapshot();
  if (state.documentPollInFlight) {
    elements.documentPollingStatus.textContent = "正在刷新文档状态...";
    return;
  }
  if (document.hidden && snapshot.shouldPoll) {
    elements.documentPollingStatus.textContent = "页面在后台，自动轮询已暂停";
    return;
  }
  if (state.documentPollTimer) {
    elements.documentPollingStatus.textContent = `自动轮询中，每 ${documentPollIntervalMs / 1000} 秒刷新一次`;
    return;
  }
  if (snapshot.shouldPoll) {
    elements.documentPollingStatus.textContent = "检测到进行中的任务，准备自动刷新";
    return;
  }
  elements.documentPollingStatus.textContent = "当前没有进行中的文档任务";
}

async function pollDocumentsOnce({ silent = true } = {}) {
  if (state.documentPollInFlight || !state.accessToken || !state.selectedCollectionId) {
    return;
  }

  state.documentPollInFlight = true;
  renderDocumentPollingState();
  try {
    await loadDocuments({ refreshSelectedDetail: Boolean(state.selectedDocumentId), silent });
  } catch (error) {
    if (!silent) {
      throw error;
    }
    window.console.error(error);
  } finally {
    state.documentPollInFlight = false;
    renderDocumentPollingState();
  }
}

function syncDocumentPolling() {
  if (!shouldPollDocuments() || document.hidden) {
    stopDocumentPolling();
    return;
  }

  if (state.documentPollTimer) {
    renderDocumentPollingState();
    return;
  }

  state.documentPollTimer = window.setInterval(async () => {
    await pollDocumentsOnce({ silent: true });
  }, documentPollIntervalMs);
  renderDocumentPollingState();
}

function setAuthenticatedUser(payload) {
  state.accessToken = payload.access_token;
  state.currentUser = payload.user;
  window.localStorage.setItem(tokenStorageKey, payload.access_token);
  clearSessionNotice();
  renderAuthState();
}

function clearDocumentDetail() {
  state.selectedDocumentId = null;
  state.selectedDocumentDetail = null;
  state.documentDetailLoading = false;
  state.documentDetailErrorMessage = "";
  renderDocuments();
  renderDocumentDetail();
}

function clearAuthentication(message = "") {
  stopStreamingAnswer();
  state.accessToken = null;
  state.currentUser = null;
  state.collections = [];
  state.conversations = [];
  state.documents = [];
  state.selectedCollectionId = "";
  state.conversationId = null;
  state.chatStreaming = false;
  state.currentStreamController = null;
  state.uploadQueue = [];
  state.uploadProcessing = false;
  state.busyDocumentIds = new Set();
  stopDocumentPolling();
  clearDocumentDetail();
  window.localStorage.removeItem(tokenStorageKey);
  if (message) {
    setSessionNotice(message);
  }
  renderAuthState();
}

function updateChatControls() {
  const disabled = state.chatStreaming;
  elements.chatInput.disabled = disabled;
  elements.chatSubmitButton.disabled = disabled;
  elements.resetConversationButton.disabled = disabled;
  elements.stopChatButton.classList.toggle("hidden", !disabled);
  elements.stopChatButton.disabled = !disabled;
  elements.chatSubmitButton.textContent = disabled ? "回答生成中..." : "发送问题";
  renderConversationList();
}

function updateUploadControls() {
  const disabled = !state.selectedCollectionId || state.uploadProcessing;
  elements.fileInput.disabled = disabled;
  elements.uploadSubmitButton.disabled = disabled;
  elements.uploadSubmitButton.textContent = state.uploadProcessing ? "上传中..." : "上传并入库";
}

function renderAuthState() {
  const authenticated = Boolean(state.accessToken && state.currentUser);
  elements.authPanel.classList.toggle("hidden", authenticated);
  elements.dashboard.classList.toggle("hidden", !authenticated);
  elements.logoutButton.classList.toggle("hidden", !authenticated);
  elements.refreshAllButton.classList.toggle("hidden", !authenticated);
  elements.currentUserCard.classList.toggle("hidden", !authenticated);

  if (authenticated) {
    elements.currentUsername.textContent = state.currentUser.username;
    elements.currentUserEmail.textContent = state.currentUser.email;
  } else {
    elements.currentUsername.textContent = "-";
    elements.currentUserEmail.textContent = "-";
    elements.conversationList.innerHTML = "";
    elements.conversationListEmptyState.style.display = "block";
    elements.documentsList.innerHTML = "";
    elements.documentsEmptyState.style.display = "block";
  }

  renderWorkspaceSummary();
  renderConversationList();
  renderUploadQueue();
  renderDocuments();
  renderDocumentDetail();
  renderDocumentPollingState();
  updateChatControls();
  updateUploadControls();
}

async function parseResponsePayload(response) {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  return response.text();
}

async function assertOkResponse(response) {
  if (response.ok) {
    return response;
  }

  const payload = await parseResponsePayload(response);
  const message = typeof payload === "string" ? payload : payload.message || "请求失败";
  if (response.status === 401) {
    clearAuthentication("登录状态已失效，请重新登录后继续操作。");
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

function createChatAbortController() {
  if (state.currentStreamController) {
    state.currentStreamController.abort();
  }
  const controller = new AbortController();
  state.currentStreamController = controller;
  return controller;
}

function clearChatAbortController(controller = null) {
  if (!controller || state.currentStreamController === controller) {
    state.currentStreamController = null;
  }
}

function stopStreamingAnswer() {
  if (!state.currentStreamController) {
    return;
  }
  state.currentStreamController.abort();
}

function renderCollectionOptions() {
  elements.collectionSelect.innerHTML = "";

  state.collections.forEach((collection) => {
    const option = document.createElement("option");
    option.value = collection.id;
    option.textContent = collection.name;
    elements.collectionSelect.appendChild(option);
  });

  if (state.selectedCollectionId && !state.collections.some((collection) => collection.id === state.selectedCollectionId)) {
    state.selectedCollectionId = state.collections[0]?.id || "";
  }

  if (!state.selectedCollectionId && state.collections.length > 0) {
    state.selectedCollectionId = state.collections[0].id;
  }

  elements.collectionSelect.value = state.selectedCollectionId || "";
  updateUploadControls();
  renderWorkspaceSummary();
}

function getConversationTitle(conversation) {
  return (conversation.title || "").trim() || "未命名会话";
}

function renderConversationList() {
  elements.conversationList.innerHTML = "";
  elements.conversationListEmptyState.style.display = state.conversations.length ? "none" : "block";

  state.conversations.forEach((conversation) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "conversation-item";
    button.disabled = state.chatStreaming;
    if (conversation.id === state.conversationId) {
      button.classList.add("selected");
    }

    const title = document.createElement("p");
    title.className = "conversation-title";
    title.textContent = getConversationTitle(conversation);

    const meta = document.createElement("div");
    meta.className = "document-meta";
    meta.textContent = `最后更新：${formatDateTime(conversation.updated_at)}`;

    button.appendChild(title);
    button.appendChild(meta);
    button.addEventListener("click", () => {
      void openConversation(conversation.id);
    });
    elements.conversationList.appendChild(button);
  });
  renderWorkspaceSummary();
}

function renderUploadQueue() {
  elements.uploadQueue.innerHTML = "";
  elements.uploadQueueEmptyState.style.display = state.uploadQueue.length ? "none" : "block";

  state.uploadQueue.forEach((item) => {
    const article = document.createElement("article");
    article.className = "upload-queue-item";

    const header = document.createElement("header");

    const titleWrap = document.createElement("div");
    const title = document.createElement("p");
    title.className = "document-name";
    title.textContent = item.filename;
    const meta = document.createElement("div");
    meta.className = "document-meta";
    meta.textContent = `${getCollectionName(item.collectionId)} · ${formatBytes(item.size)}`;
    titleWrap.appendChild(title);
    titleWrap.appendChild(meta);

    const status = document.createElement("span");
    status.className = badgeClass(item.status);
    status.textContent = formatStatusLabel(item.status);

    header.appendChild(titleWrap);
    header.appendChild(status);
    article.appendChild(header);

    const message = document.createElement("div");
    message.className = "upload-queue-message";
    message.textContent = item.message || "等待处理。";
    article.appendChild(message);

    const footnote = document.createElement("div");
    footnote.className = "document-meta";
    footnote.textContent = `最近更新：${formatDateTime(item.updatedAt)}`;
    article.appendChild(footnote);

    elements.uploadQueue.appendChild(article);
  });
  renderWorkspaceSummary();
}

function createDocumentActionButton(label, className, onClick, disabled = false) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = className;
  button.textContent = label;
  button.disabled = disabled;
  button.addEventListener("click", onClick);
  return button;
}

function renderDocuments() {
  elements.documentsList.innerHTML = "";
  elements.documentsEmptyState.style.display = state.documents.length ? "none" : "block";

  state.documents.forEach((documentItem) => {
    const card = document.createElement("article");
    card.className = "document-card";
    if (state.selectedDocumentId === documentItem.id) {
      card.classList.add("selected");
    }

    const header = document.createElement("header");
    const info = document.createElement("div");
    const name = document.createElement("p");
    name.className = "document-name";
    name.textContent = documentItem.filename;
    const meta = document.createElement("div");
    meta.className = "document-meta";
    meta.textContent = formatDocumentMeta(documentItem);
    info.appendChild(name);
    info.appendChild(meta);

    const status = document.createElement("span");
    status.className = badgeClass(documentItem.status);
    status.textContent = formatStatusLabel(documentItem.status);

    header.appendChild(info);
    header.appendChild(status);
    card.appendChild(header);

    const body = document.createElement("div");
    body.className = "document-card-body";

    const statusCopy = document.createElement("p");
    statusCopy.className = "document-status-copy";
    statusCopy.textContent = buildDocumentStatusCopy(documentItem).trim();
    body.appendChild(statusCopy);

    if (documentItem.error_message) {
      const errorMeta = document.createElement("div");
      errorMeta.className = "detail-alert";
      errorMeta.textContent = `失败原因：${documentItem.error_message}`;
      body.appendChild(errorMeta);
    }

    const updatedMeta = document.createElement("div");
    updatedMeta.className = "document-meta";
    updatedMeta.textContent = `最近更新：${formatDateTime(documentItem.updated_at)}`;
    body.appendChild(updatedMeta);

    card.appendChild(body);

    const busy = state.busyDocumentIds.has(documentItem.id);
    const actions = document.createElement("div");
    actions.className = "document-actions";
    actions.appendChild(
      createDocumentActionButton("详情", "ghost-button mini-button", () => {
        void openDocumentDetail(documentItem.id);
      }),
    );
    actions.appendChild(
      createDocumentActionButton(
        "重试入库",
        "ghost-button mini-button",
        () => {
          void retryDocument(documentItem);
        },
        busy || ["queued", "processing"].includes(documentItem.status),
      ),
    );
    actions.appendChild(
      createDocumentActionButton(
        "删除",
        "danger-button mini-button",
        () => {
          void deleteDocument(documentItem);
        },
        busy,
      ),
    );
    card.appendChild(actions);

    elements.documentsList.appendChild(card);
  });
  renderWorkspaceSummary();
}

function renderDocumentMetaGrid(detail) {
  elements.documentDetailMeta.innerHTML = "";
  const rows = [
    ["文件名", detail.filename],
    ["知识库", getCollectionName(detail.collection_id)],
    ["文件类型", detail.file_type.toUpperCase()],
    ["文件大小", formatBytes(detail.file_size)],
    ["分块数", String(detail.chunk_count)],
    ["创建时间", formatDateTime(detail.created_at)],
    ["更新时间", formatDateTime(detail.updated_at)],
    ["文件路径", detail.file_path],
  ];

  rows.forEach(([label, value]) => {
    const item = document.createElement("div");
    item.className = "detail-meta-item";

    const title = document.createElement("span");
    title.className = "detail-meta-label";
    title.textContent = label;

    const body = document.createElement("strong");
    body.className = "detail-meta-value";
    body.textContent = value;

    item.appendChild(title);
    item.appendChild(body);
    elements.documentDetailMeta.appendChild(item);
  });
}

function buildChunkPreviewEmptyMessage(detail) {
  if (state.documentDetailLoading) {
    return "正在加载文档详情和分块预览...";
  }
  if (state.documentDetailErrorMessage) {
    return "文档详情加载失败，请稍后重试。";
  }
  if (!detail) {
    return "选择文档后可查看分块预览。";
  }
  if (detail.status !== "indexed" && detail.chunk_preview.length === 0) {
    return "文档尚未完成入库，当前还没有可预览的分块。";
  }
  if (detail.chunk_preview.length === 0) {
    return "没有查询到可预览的分块。";
  }
  return "";
}

function renderDocumentDetail() {
  const snapshot = state.documents.find((item) => item.id === state.selectedDocumentId) || null;
  const detail = state.selectedDocumentDetail || snapshot;

  if (!state.selectedDocumentId && !state.documentDetailLoading) {
    elements.documentDetailPanel.classList.add("hidden");
    return;
  }

  elements.documentDetailPanel.classList.remove("hidden");
  elements.documentDetailTitle.textContent = detail?.filename || "文档详情";
  elements.documentDetailStatus.className = badgeClass(detail?.status || "unknown");
  elements.documentDetailStatus.textContent = formatStatusLabel(detail?.status || "loading");

  if (detail) {
    renderDocumentMetaGrid(detail);
  } else {
    elements.documentDetailMeta.innerHTML = "";
  }

  const alertMessages = [];
  if (detail?.error_message) {
    alertMessages.push(`入库失败：${detail.error_message}`);
  }
  if (detail?.chunk_preview_error) {
    alertMessages.push(`分块预览加载失败：${detail.chunk_preview_error}`);
  }
  if (state.documentDetailErrorMessage) {
    alertMessages.push(state.documentDetailErrorMessage);
  }

  if (alertMessages.length) {
    elements.documentDetailError.textContent = alertMessages.join(" ");
    elements.documentDetailError.classList.remove("hidden");
  } else {
    elements.documentDetailError.textContent = "";
    elements.documentDetailError.classList.add("hidden");
  }

  const previewChunks = detail?.chunk_preview || [];
  if (detail) {
    const previewCount = previewChunks.length;
    const summary =
      detail.chunk_count > previewCount && previewCount > 0
        ? `当前展示前 ${previewCount} / ${detail.chunk_count} 个分块`
        : `当前展示 ${previewCount} 个分块`;
    elements.documentChunkPreviewSummary.textContent = summary;
  } else {
    elements.documentChunkPreviewSummary.textContent = "";
  }

  elements.documentChunkPreview.innerHTML = "";
  const emptyMessage = buildChunkPreviewEmptyMessage(detail);
  elements.documentChunkPreviewEmptyState.style.display = previewChunks.length ? "none" : "block";
  elements.documentChunkPreviewEmptyState.textContent = emptyMessage;

  previewChunks.forEach((chunk) => {
    const card = document.createElement("article");
    card.className = "chunk-card";

    const header = document.createElement("div");
    header.className = "chunk-card-header";
    const title = document.createElement("strong");
    title.textContent = `Chunk #${chunk.chunk_index}`;
    const source = document.createElement("span");
    source.className = "document-meta";
    source.textContent = chunk.source_name;
    header.appendChild(title);
    header.appendChild(source);

    const body = document.createElement("pre");
    body.className = "chunk-card-body";
    body.textContent = chunk.content;

    card.appendChild(header);
    card.appendChild(body);
    elements.documentChunkPreview.appendChild(card);
  });
}

function renderSources(container, sources = []) {
  container.innerHTML = "";
  if (!sources.length) {
    return;
  }

  sources.forEach((source) => {
    const item = document.createElement("div");
    item.className = "source-item";

    const title = document.createElement("strong");
    title.textContent = source.source_name;

    const meta = document.createElement("div");
    meta.textContent = `片段 ${source.chunk_index}${source.score ? ` · 相关度 ${source.score.toFixed(3)}` : ""}`;

    const content = document.createElement("div");
    content.textContent = source.content;

    item.appendChild(title);
    item.appendChild(meta);
    item.appendChild(content);
    container.appendChild(item);
  });
}

function createMessageElement(role, body = "", sources = []) {
  const article = document.createElement("article");
  article.className = `message ${role}`;

  const roleEl = document.createElement("div");
  roleEl.className = "message-role";
  roleEl.textContent = role === "user" ? "你" : role === "assistant" ? "助手" : "系统";

  const bodyEl = document.createElement("div");
  bodyEl.className = "message-body";
  bodyEl.textContent = body;

  const sourcesEl = document.createElement("div");
  sourcesEl.className = "source-list";

  article.appendChild(roleEl);
  article.appendChild(bodyEl);
  article.appendChild(sourcesEl);

  const messageRef = {
    article,
    bodyEl,
    sourcesEl,
    body,
  };
  updateMessage(messageRef, { body, sources });
  return messageRef;
}

function updateMessage(messageRef, { body, sources, streaming } = {}) {
  if (typeof body === "string") {
    messageRef.body = body;
    messageRef.bodyEl.textContent = body;
  }
  if (Array.isArray(sources)) {
    renderSources(messageRef.sourcesEl, sources);
  }
  if (typeof streaming === "boolean") {
    messageRef.article.classList.toggle("streaming", streaming);
  }
}

function appendMessage(role, body = "", sources = []) {
  const messageRef = createMessageElement(role, body, sources);
  elements.chatFeed.appendChild(messageRef.article);
  elements.chatFeed.scrollTop = elements.chatFeed.scrollHeight;
  return messageRef;
}

function resetChatFeed() {
  elements.chatFeed.innerHTML = "";
  appendMessage("system", "欢迎来到 ChatRobot_v3。选择知识库并上传文档后，就可以开始基于私有知识库的问答。");
}

function hydrateChatFeed(messages) {
  elements.chatFeed.innerHTML = "";
  if (!messages.length) {
    resetChatFeed();
    return;
  }

  messages.forEach((message) => {
    appendMessage(message.role, message.content, message.sources || []);
  });
}

function setDocumentBusy(documentId, busy) {
  if (busy) {
    state.busyDocumentIds.add(documentId);
  } else {
    state.busyDocumentIds.delete(documentId);
  }
  renderDocuments();
}

function updateUploadQueueEntry(entryId, updates) {
  state.uploadQueue = state.uploadQueue.map((item) =>
    item.id === entryId
      ? {
          ...item,
          ...updates,
          updatedAt: new Date().toISOString(),
        }
      : item,
  );
  renderUploadQueue();
  syncDocumentPolling();
}

function trackDocumentTask(taskRecord, message) {
  const existing = state.uploadQueue.find((item) => item.documentId === taskRecord.id);
  const nextItem = {
    id: existing?.id || `upload-queue-${state.uploadQueueSeed++}`,
    documentId: taskRecord.id,
    filename: taskRecord.filename,
    size: taskRecord.file_size,
    collectionId: taskRecord.collection_id,
    status: taskRecord.status || taskRecord.task_status || "queued",
    message: message || buildDocumentStatusCopy(taskRecord).trim(),
    updatedAt: new Date().toISOString(),
  };

  if (existing) {
    state.uploadQueue = state.uploadQueue.map((item) =>
      item.documentId === taskRecord.id ? { ...item, ...nextItem } : item,
    );
  } else {
    state.uploadQueue = [nextItem, ...state.uploadQueue];
  }
  renderUploadQueue();
  syncDocumentPolling();
}

function markQueueEntryDeleted(documentId) {
  let changed = false;
  state.uploadQueue = state.uploadQueue.map((item) => {
    if (item.documentId !== documentId) {
      return item;
    }
    changed = true;
    return {
      ...item,
      status: "deleted",
      message: "文档已删除。",
      updatedAt: new Date().toISOString(),
    };
  });
  if (changed) {
    renderUploadQueue();
    syncDocumentPolling();
  }
}

function syncUploadQueueWithDocuments() {
  const documentsById = new Map(state.documents.map((item) => [item.id, item]));
  let changed = false;
  state.uploadQueue = state.uploadQueue.map((item) => {
    if (!item.documentId) {
      return item;
    }

    const documentItem = documentsById.get(item.documentId);
    if (!documentItem) {
      return item;
    }

    const nextMessage = buildDocumentStatusCopy(documentItem).trim();
    if (
      item.status === documentItem.status &&
      item.message === nextMessage &&
      item.size === documentItem.file_size &&
      item.filename === documentItem.filename
    ) {
      return item;
    }

    changed = true;
    return {
      ...item,
      filename: documentItem.filename,
      size: documentItem.file_size,
      status: documentItem.status,
      message: nextMessage,
      updatedAt: new Date().toISOString(),
    };
  });

  if (changed) {
    renderUploadQueue();
  }
  renderDocumentPollingState();
}

async function loadCurrentUser() {
  const currentUser = await request(`${apiPrefix}/auth/me`);
  state.currentUser = currentUser;
  clearSessionNotice();
  renderAuthState();
}

async function loadCollections() {
  state.collections = await request(`${apiPrefix}/collections`);
  renderCollectionOptions();
}

async function loadConversations({ selectConversationId = state.conversationId, silent = false } = {}) {
  if (!state.selectedCollectionId) {
    state.conversations = [];
    state.conversationId = null;
    renderConversationList();
    resetChatFeed();
    return;
  }

  try {
    state.conversations = await request(
      `${apiPrefix}/conversations?collection_id=${encodeURIComponent(state.selectedCollectionId)}`,
    );

    if (
      selectConversationId &&
      state.conversations.some((conversation) => conversation.id === selectConversationId)
    ) {
      state.conversationId = selectConversationId;
    } else if (
      state.conversationId &&
      !state.conversations.some((conversation) => conversation.id === state.conversationId)
    ) {
      state.conversationId = null;
      resetChatFeed();
    }

    renderConversationList();
  } catch (error) {
    if (!silent) {
      throw error;
    }
    window.console.error(error);
  }
}

async function openConversation(conversationId) {
  const detail = await request(`${apiPrefix}/conversations/${encodeURIComponent(conversationId)}`);
  state.conversationId = detail.id;
  renderConversationList();
  hydrateChatFeed(detail.messages || []);
}

async function loadSelectedDocumentDetail({ silent = false } = {}) {
  if (!state.selectedDocumentId) {
    return;
  }

  state.documentDetailLoading = true;
  state.documentDetailErrorMessage = "";
  renderDocumentDetail();

  try {
    const detail = await request(`${apiPrefix}/documents/${encodeURIComponent(state.selectedDocumentId)}`);
    state.selectedDocumentDetail = detail;
    state.documentDetailErrorMessage = "";
  } catch (error) {
    state.selectedDocumentDetail = null;
    state.documentDetailErrorMessage = error.message || "文档详情加载失败。";
    if (!silent) {
      showToast(state.documentDetailErrorMessage, true);
    }
  } finally {
    state.documentDetailLoading = false;
    renderDocuments();
    renderDocumentDetail();
  }
}

async function openDocumentDetail(documentId) {
  state.selectedDocumentId = documentId;
  state.selectedDocumentDetail = null;
  state.documentDetailErrorMessage = "";
  state.documentDetailLoading = true;
  renderDocuments();
  renderDocumentDetail();
  await loadSelectedDocumentDetail();
}

async function loadDocuments({ refreshSelectedDetail = false, silent = false } = {}) {
  if (!state.selectedCollectionId) {
    state.documents = [];
    renderDocuments();
    if (!silent) {
      renderDocumentDetail();
    }
    renderDocumentPollingState();
    syncDocumentPolling();
    updateUploadControls();
    return;
  }

  try {
    state.documents = await request(
      `${apiPrefix}/documents?collection_id=${encodeURIComponent(state.selectedCollectionId)}`,
    );
    syncUploadQueueWithDocuments();
    renderDocuments();

    if (
      state.selectedDocumentId &&
      !state.documents.some((documentItem) => documentItem.id === state.selectedDocumentId)
    ) {
      clearDocumentDetail();
    } else if (refreshSelectedDetail && state.selectedDocumentId) {
      await loadSelectedDocumentDetail({ silent: true });
    } else {
      renderDocumentDetail();
    }
  } catch (error) {
    if (!silent) {
      throw error;
    }
    window.console.error(error);
  } finally {
    renderDocumentPollingState();
    syncDocumentPolling();
    updateUploadControls();
  }
}

async function refreshAll() {
  await loadCollections();
  await loadConversations();
  await loadDocuments({ refreshSelectedDetail: Boolean(state.selectedDocumentId) });
}

function createUploadQueueEntries(files) {
  return files.map((file) => ({
    id: `upload-local-${state.uploadQueueSeed++}`,
    filename: file.name,
    size: file.size,
    file,
    collectionId: state.selectedCollectionId,
    status: "waiting",
    message: "等待上传到服务器。",
    documentId: null,
    updatedAt: new Date().toISOString(),
  }));
}

async function uploadQueuedFile(queueEntry) {
  updateUploadQueueEntry(queueEntry.id, {
    status: "uploading",
    message: "正在上传文件并创建入库任务。",
  });

  const formData = new FormData();
  formData.append("collection_id", queueEntry.collectionId);
  formData.append("file", queueEntry.file);

  try {
    const result = await request(`${apiPrefix}/documents/upload`, {
      method: "POST",
      body: formData,
    });

    updateUploadQueueEntry(queueEntry.id, {
      documentId: result.id,
      filename: result.filename,
      size: result.file_size,
      status: result.status || result.task_status || "queued",
      message: `已进入入库队列，任务状态：${result.task_status || result.status}。`,
    });

    if (queueEntry.collectionId === state.selectedCollectionId) {
      await loadDocuments({ refreshSelectedDetail: Boolean(state.selectedDocumentId), silent: true });
    }
  } catch (error) {
    updateUploadQueueEntry(queueEntry.id, {
      status: "failed",
      message: error.message || "上传失败。",
    });
    showToast(`文件 ${queueEntry.filename} 上传失败：${error.message}`, true);
  }
}

async function processUploadQueue() {
  if (state.uploadProcessing) {
    return;
  }

  state.uploadProcessing = true;
  updateUploadControls();
  syncDocumentPolling();

  try {
    let nextItem = state.uploadQueue.find((item) => item.status === "waiting");
    while (nextItem) {
      await uploadQueuedFile(nextItem);
      nextItem = state.uploadQueue.find((item) => item.status === "waiting");
    }
  } finally {
    state.uploadProcessing = false;
    updateUploadControls();
    syncDocumentPolling();
  }
}

async function deleteDocument(documentItem) {
  if (!window.confirm(`确认删除文档《${documentItem.filename}》吗？这会同时移除已入库的向量数据。`)) {
    return;
  }

  setDocumentBusy(documentItem.id, true);
  try {
    await request(`${apiPrefix}/documents/${encodeURIComponent(documentItem.id)}`, {
      method: "DELETE",
    });
    markQueueEntryDeleted(documentItem.id);
    if (state.selectedDocumentId === documentItem.id) {
      clearDocumentDetail();
    }
    await loadDocuments({ refreshSelectedDetail: Boolean(state.selectedDocumentId), silent: true });
    showToast(`文档 ${documentItem.filename} 已删除。`);
  } catch (error) {
    showToast(error.message, true);
  } finally {
    setDocumentBusy(documentItem.id, false);
  }
}

async function retryDocument(documentItem) {
  setDocumentBusy(documentItem.id, true);
  try {
    const result = await request(`${apiPrefix}/documents/${encodeURIComponent(documentItem.id)}/retry`, {
      method: "POST",
    });
    trackDocumentTask(result, "已重新加入入库队列。");
    await loadDocuments({ refreshSelectedDetail: state.selectedDocumentId === documentItem.id, silent: true });
    showToast(`文档 ${documentItem.filename} 已重新加入入库队列。`);
  } catch (error) {
    showToast(error.message, true);
  } finally {
    setDocumentBusy(documentItem.id, false);
  }
}

function parseSseChunk(rawChunk) {
  const lines = rawChunk.split("\n");
  let eventName = "message";
  const dataLines = [];

  lines.forEach((line) => {
    if (!line) {
      return;
    }
    if (line.startsWith("event:")) {
      eventName = line.slice(6).trim();
      return;
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  });

  if (!dataLines.length) {
    return null;
  }

  const rawData = dataLines.join("\n");
  let payload = rawData;
  try {
    payload = JSON.parse(rawData);
  } catch (_error) {
    payload = rawData;
  }

  return { eventName, payload };
}

async function consumeSse(response, onEvent) {
  if (!response.body) {
    throw new Error("当前浏览器不支持流式响应读取。");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    buffer = buffer.replace(/\r\n/g, "\n");

    let delimiterIndex = buffer.indexOf("\n\n");
    while (delimiterIndex !== -1) {
      const chunk = buffer.slice(0, delimiterIndex).trim();
      buffer = buffer.slice(delimiterIndex + 2);
      if (chunk) {
        const parsed = parseSseChunk(chunk);
        if (parsed) {
          onEvent(parsed.eventName, parsed.payload);
        }
      }
      delimiterIndex = buffer.indexOf("\n\n");
    }

    if (done) {
      break;
    }
  }

  const trailingChunk = buffer.trim();
  if (trailingChunk) {
    const parsed = parseSseChunk(trailingChunk);
    if (parsed) {
      onEvent(parsed.eventName, parsed.payload);
    }
  }
}

async function streamChatCompletion(query, assistantMessage, signal) {
  const headers = new Headers({ "Content-Type": "application/json" });
  if (state.accessToken) {
    headers.set("Authorization", `Bearer ${state.accessToken}`);
  }

  const response = await fetch(`${apiPrefix}/chat/completions`, {
    method: "POST",
    headers,
    signal,
    body: JSON.stringify({
      query,
      collection_id: state.selectedCollectionId,
      conversation_id: state.conversationId,
      stream: true,
    }),
  });

  await assertOkResponse(response);

  let streamedAnswer = "";
  let streamError = null;

  updateMessage(assistantMessage, {
    body: "正在生成回答...",
    sources: [],
    streaming: true,
  });

  await consumeSse(response, (eventName, payload) => {
    if (eventName === "start") {
      state.conversationId = payload.conversation_id;
      void loadConversations({ selectConversationId: state.conversationId, silent: true });
      return;
    }

    if (eventName === "token") {
      const delta = payload.delta || "";
      streamedAnswer += delta;
      updateMessage(assistantMessage, {
        body: streamedAnswer || "正在生成回答...",
        streaming: true,
      });
      elements.chatFeed.scrollTop = elements.chatFeed.scrollHeight;
      return;
    }

    if (eventName === "sources") {
      updateMessage(assistantMessage, {
        body: streamedAnswer || "本次没有返回正文内容。",
        sources: payload.sources || [],
        streaming: true,
      });
      return;
    }

    if (eventName === "done") {
      state.conversationId = payload.conversation_id || state.conversationId;
      void loadConversations({ selectConversationId: state.conversationId, silent: true });
      updateMessage(assistantMessage, {
        body: payload.answer || streamedAnswer || "本次没有返回正文内容。",
        streaming: false,
      });
      return;
    }

    if (eventName === "error") {
      streamError = new Error(payload.message || "流式输出失败");
    }
  });

  if (streamError) {
    throw streamError;
  }
}

async function submitChatWithFallback(query, assistantMessage) {
  const controller = createChatAbortController();
  if (!window.ReadableStream) {
    const result = await request(`${apiPrefix}/chat/completions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: controller.signal,
      body: JSON.stringify({
        query,
        collection_id: state.selectedCollectionId,
        conversation_id: state.conversationId,
      }),
    });
    state.conversationId = result.conversation_id;
    updateMessage(assistantMessage, {
      body: result.answer,
      sources: result.sources || [],
      streaming: false,
    });
    await loadConversations({ selectConversationId: state.conversationId, silent: true });
    clearChatAbortController(controller);
    return;
  }

  try {
    await streamChatCompletion(query, assistantMessage, controller.signal);
  } finally {
    clearChatAbortController(controller);
  }
}

elements.loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const formData = new URLSearchParams();
    formData.set("username", elements.loginIdentifierInput.value.trim());
    formData.set("password", elements.loginPasswordInput.value);

    const result = await request(`${apiPrefix}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: formData.toString(),
      includeAuth: false,
    });
    setAuthenticatedUser(result);
    elements.loginForm.reset();
    await refreshAll();
    showToast("登录成功，已自动加载你的个人知识库。");
  } catch (error) {
    showToast(error.message, true);
  }
});

elements.logoutButton.addEventListener("click", () => {
  clearAuthentication("你已退出登录。");
  showToast("已退出登录。");
});

elements.collectionSelect.addEventListener("change", async (event) => {
  state.selectedCollectionId = event.target.value;
  state.conversationId = null;
  clearDocumentDetail();
  resetChatFeed();
  await loadConversations({ silent: true });
  await loadDocuments({ refreshSelectedDetail: false });
  showToast("已切换知识库，会话和文档详情已同步刷新。");
});

elements.collectionForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const name = elements.collectionNameInput.value.trim();
  const description = elements.collectionDescriptionInput.value.trim();
  if (!name) {
    showToast("请输入知识库名称。", true);
    return;
  }
  try {
    const collection = await request(`${apiPrefix}/collections`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, description: description || null }),
    });
    state.selectedCollectionId = collection.id;
    elements.collectionForm.reset();
    await refreshAll();
    showToast(`知识库 ${collection.name} 已创建。`);
  } catch (error) {
    showToast(error.message, true);
  }
});

elements.uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.selectedCollectionId) {
    showToast("请先选择知识库。", true);
    return;
  }

  const files = Array.from(elements.fileInput.files || []);
  if (!files.length) {
    showToast("请先选择至少一个文件。", true);
    return;
  }

  const queuedEntries = createUploadQueueEntries(files);
  state.uploadQueue = [...queuedEntries, ...state.uploadQueue];
  renderUploadQueue();
  syncDocumentPolling();

  elements.uploadForm.reset();
  updateUploadControls();
  showToast(`已加入 ${files.length} 个上传任务。`);

  await processUploadQueue();
});

elements.chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = elements.chatInput.value.trim();
  if (!state.selectedCollectionId) {
    showToast("请先选择知识库。", true);
    return;
  }
  if (!query) {
    showToast("请输入问题。", true);
    return;
  }
  if (state.chatStreaming) {
    showToast("当前回答尚未结束，请稍候。", true);
    return;
  }

  appendMessage("user", query);
  const assistantMessage = appendMessage("assistant", "");
  elements.chatInput.value = "";
  state.chatStreaming = true;
  updateChatControls();

  try {
    await submitChatWithFallback(query, assistantMessage);
  } catch (error) {
    const interrupted = error?.name === "AbortError";
    const fallbackText = interrupted
      ? assistantMessage.body
        ? `${assistantMessage.body}\n\n[回答已由你手动中断]`
        : "[回答已由你手动中断]"
      : assistantMessage.body
        ? `${assistantMessage.body}\n\n[流式输出中断：${error.message}]`
        : `请求失败：${error.message}`;
    updateMessage(assistantMessage, {
      body: fallbackText,
      streaming: false,
    });
    if (interrupted) {
      showToast("已中断当前回答。");
    } else {
      showToast(error.message, true);
    }
  } finally {
    state.chatStreaming = false;
    state.currentStreamController = null;
    updateChatControls();
  }
});

elements.refreshAllButton.addEventListener("click", async () => {
  if (!state.accessToken) {
    showToast("请先登录。", true);
    return;
  }
  try {
    await loadCurrentUser();
    await refreshAll();
    showToast("个人知识库和文档状态已刷新。");
  } catch (error) {
    showToast(error.message, true);
  }
});

elements.refreshDocumentsButton.addEventListener("click", async () => {
  if (!state.selectedCollectionId) {
    showToast("请先选择知识库。", true);
    return;
  }
  try {
    await loadDocuments({ refreshSelectedDetail: Boolean(state.selectedDocumentId) });
    showToast("文档列表已刷新。");
  } catch (error) {
    showToast(error.message, true);
  }
});

document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    syncDocumentPolling();
    return;
  }
  syncDocumentPolling();
  if (shouldPollDocuments()) {
    void pollDocumentsOnce({ silent: true });
  }
});

window.addEventListener("focus", () => {
  if (shouldPollDocuments()) {
    void pollDocumentsOnce({ silent: true });
  }
});

elements.stopChatButton.addEventListener("click", () => {
  stopStreamingAnswer();
});

elements.resetConversationButton.addEventListener("click", () => {
  state.conversationId = null;
  renderConversationList();
  resetChatFeed();
  showToast("已开始新的会话。");
});

elements.closeDocumentDetailButton.addEventListener("click", () => {
  clearDocumentDetail();
});

async function bootstrap() {
  renderAuthState();
  const initialAuthNotice = readInitialAuthNotice();
  if (initialAuthNotice) {
    setSessionNotice(initialAuthNotice);
  } else {
    renderSessionNotice();
  }
  resetChatFeed();

  if (!state.accessToken) {
    return;
  }

  try {
    await loadCurrentUser();
    await refreshAll();
    showToast("已自动恢复登录状态，并加载你的个人知识库。");
  } catch (error) {
    showToast(error.message, true);
  }
}

bootstrap();
