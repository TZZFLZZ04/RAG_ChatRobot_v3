# ChatRobot_v3 项目面试准备文档（开发者视角）

> 本文基于 `d:\Dify\LangChain\ChatRobot_v3` 真实代码撰写，所有文件路径、函数名、配置项均可在仓库中直接核对。文档面向"项目实现经历"类面试，按"定位 → 技术栈 → 架构 → 流程 → 难点 → 亮点 → 不足 → STAR → 量化 → 提问清单"十段递进展开。

---

## 第一章 项目一句话定位

ChatRobot_v3 是一个面向**企业知识问答场景**的 RAG（Retrieval-Augmented Generation）应用，基于 `FastAPI + PostgreSQL + SQLAlchemy + Celery + Redis` 构建，支持 `FAISS / Milvus` 双向量后端切换，提供从「文档上传 → 异步入库 → 混合检索 → 流式问答 → RAG 评估」的完整闭环。

一句话能讲清楚的边界：

- 它**不是**通用聊天机器人，而是基于**私有知识库**的问答系统，所有回答都期望有来源（sources）可追溯。
- 它**不是**单机脚本，而是**多模块服务**：FastAPI 提供 HTTP/SSE 接口，Celery + Redis 承担异步入库，PostgreSQL 存元数据与对话，FAISS/Milvus 存向量。
- 它**不是**"只能跑 demo"的原型，而是带**可观测性**（Prometheus 指标 + 结构化日志 + OpenTelemetry tracing + X-Request-ID 透传）、**多租户隔离**（owner_id）、**RAG 评估闭环**（6 项检索指标 + 答案质量 + 可选 LLM judge）的工程化项目。

入口文件 `app/main.py`，路由聚合在 `app/api/v1/router.py`，Celery 入口在 `app/workers/celery_app.py` 与 `app/workers/tasks.py`。

---

## 第二章 技术栈总览

依据 `d:\Dify\LangChain\ChatRobot_v3\requirements.txt` 的真实依赖列表（共 28 条），逐项说明选型理由：

| 依赖 | 用途 | 选型理由 |
| --- | --- | --- |
| `fastapi` | Web 框架 | 现代异步 ASGI 框架，原生支持 OpenAPI 文档、依赖注入（`Depends`）、`StreamingResponse`，适合做 SSE 与 REST API |
| `uvicorn[standard]` | ASGI 服务器 | FastAPI 官方推荐运行时，`[standard]` 包含 `httptools`/`uvloop`/`websockets` 等性能加速组件 |
| `pydantic` | 数据校验 | FastAPI 内建依赖，用于 `app/schemas/` 下所有请求/响应模型 |
| `pydantic-settings` | 配置管理 | `app/core/config.py` 用 `BaseSettings` 从环境变量加载配置，支持 `.env` 与类型校验 |
| `python-multipart` | 文件上传 | FastAPI `UploadFile` 的底层依赖，文档上传接口必需 |
| `sqlalchemy` | ORM | `app/db/` 下定义 Base/Session 与 ORM 模型，`app/repositories/` 仓储层封装查询 |
| `alembic` | 数据库迁移 | `alembic/versions/20260428_01_bootstrap_current_schema.py` 实现 schema bootstrap，兼容旧库升级 |
| `psycopg2-binary` | PostgreSQL 驱动 | SQLAlchemy 连接 PG 的同步驱动，`-binary` 自带二进制无需编译 |
| `celery[redis]` | 异步任务队列 | `app/workers/` 下定义 Celery app 与任务，承担文档异步入库 |
| `redis` | 消息中间件 / 缓存 | Celery 的 broker 与 backend，同时可作通用缓存 |
| `prometheus-client` | 指标暴露 | `app/core/metrics.py` 定义 `chatrobot_http_requests_total`、`chatrobot_celery_tasks_total` 等指标，`/metrics` 端点导出 |
| `opentelemetry-api` | 追踪 API | OpenTelemetry 标准接口 |
| `opentelemetry-sdk` | 追踪 SDK | 提供 TracerProvider/SpanProcessor 实现 |
| `opentelemetry-exporter-otlp-proto-http` | 追踪导出 | 通过 OTLP HTTP 协议导出 span 到 Collector |
| `opentelemetry-instrumentation-fastapi` | FastAPI 自动埋点 | 自动为 HTTP 请求创建 span |
| `opentelemetry-instrumentation-celery` | Celery 自动埋点 | 自动为任务创建 span |
| `opentelemetry-instrumentation-sqlalchemy` | SQLAlchemy 自动埋点 | 自动为 SQL 查询创建 span |
| `langchain` | RAG 工具链基础 | 提供 LLM 抽象、文档模型、向量存储接口等 |
| `langchain-openai` | OpenAI LLM 封装 | `ChatOpenAI` 封装，被 `app/services/chat_service.py` 与 `embedding_service.py` 使用 |
| `langchain-community` | 社区集成 | 提供 `FAISS` 向量存储实现、文档加载器等 |
| `langchain-text-splitters` | 文本切分 | `RecursiveCharacterTextSplitter`，被 `app/rag/splitters.py` 使用 |
| `openai` | OpenAI API SDK | 直接调用 OpenAI 接口（embedding 与 chat） |
| `faiss-cpu` | 本地向量检索 | FAISS 索引，`app/vectorstores/faiss_store.py` 后端实现基础 |
| `pymilvus` | Milvus 客户端 | `app/vectorstores/milvus_store.py` 后端实现基础 |
| `pypdf` | PDF 解析 | `app/rag/loaders.py` 加载 PDF 文档 |
| `docx2txt` | DOCX 解析 | `app/rag/loaders.py` 加载 DOCX 文档 |
| `pytest` | 测试框架 | `tests/` 目录下 17 个测试文件，最近一次完整验证 66 passed / 1 skipped |
| `httpx` | HTTP 测试客户端 | `TestClient` 底层依赖，用于 FastAPI 接口测试 |

> **特别说明**：项目**未引入 `PyJWT`**，JWT 实现是手写的（见 `app/core/security.py`），这是项目的一个刻意设计选择（见第六章亮点 4 与第五章 5.1）。

---

## 第三章 整体架构分层

项目根目录 `app/` 下采用经典分层架构，依赖方向严格单向。完整目录树如下（仅列关键模块）：

```
app/
├── api/v1/            # FastAPI 路由层
├── schemas/           # Pydantic 请求/响应模型
├── services/          # 业务服务层
├── repositories/      # PostgreSQL 仓储层
├── db/                # SQLAlchemy Base/Session/ORM 模型
├── rag/               # RAG 工具（loaders/splitters/prompts/retrieval）
├── vectorstores/      # 向量后端（base/faiss_store/milvus_store）
├── workers/           # Celery app 与 tasks
├── core/              # 基础设施（config/exceptions/logging/metrics/...）
├── frontend/          # HTML/CSS/JS 前端
├── web/               # 前端页面路由
└── main.py            # FastAPI 应用入口
```

### 3.1 各层职责

#### `app/api/v1/`：FastAPI 路由层
负责 HTTP 协议适配、参数校验（依赖 `schemas/`）、调用 `services/`、返回响应。包含以下 router：
- `auth.py`：注册/登录/token 校验
- `chat.py`：聊天接口，含 SSE 流式（`stream_chat`）与非流式（`chat`）
- `collections.py`：知识库集合 CRUD
- `conversations.py`：会话与消息管理
- `documents.py`：文档上传/查询/删除
- `health.py`：健康检查与依赖探测
- `rag_evaluations.py`：RAG 评估任务与报告查询
- `router.py`：聚合上述 router 挂载到 `/api/v1` 前缀

#### `app/schemas/`：Pydantic 模型
定义所有 API 的请求/响应结构，与 ORM 模型解耦：
- `auth.py`：`RegisterRequest` / `LoginRequest` / `TokenResponse` 等
- `chat.py`：`ChatRequest` / `ChatResponse` / `Source` / `TokenUsage`
- `collection.py`：`CollectionCreate` / `CollectionResponse`
- `document.py`：`DocumentResponse` / `DocumentStatus` 枚举
- `common.py`：通用分页/响应包装
- `rag_eval.py`：评估任务请求/响应/报告结构

#### `app/services/`：业务服务层
项目核心业务逻辑所在，依赖注入仓储与 RAG 工具：
- `chat_service.py`：聊天主流程（`chat` / `stream_chat` / `_rewrite_query_for_retrieval` / `_build_messages` / `_build_sources` / `_extract_token_usage`）
- `collection_service.py`：知识库集合管理
- `conversation_service.py`：会话与消息管理（`get_or_create` 按 owner_id 隔离）
- `document_service.py`：文档上传与状态机管理（`build_document_storage_path`）
- `embedding_service.py`：embedding 调用封装
- `ingestion_service.py`：文档入库主流程（`ingest_document`：加载 → 切分 → 写向量库 → 状态回写）
- `rag_evaluation_service.py`：RAG 评估执行（检索指标 + 答案质量 + LLM judge）
- `rag_evaluation_report_service.py`：评估报告生成与持久化
- `retrieval_service.py`：检索编排（Hybrid + RRF + Rerank + Query Rewrite 的开关与组合）
- `task_queue_service.py`：Celery 任务投递（`enqueue_document_ingestion` 透传 request_id）
- `user_service.py`：用户注册/认证
- `vector_store_service.py`：向量后端工厂（`_get_backend` 根据 `vector_backend` 选择 FAISS/Milvus）

#### `app/repositories/`：PostgreSQL 仓储层
封装 SQLAlchemy 查询，所有 SQL 集中在此层：
- `base.py`：`BaseRepository` 通用 CRUD
- `collection_repository.py`：集合查询，按 `owner_id` 过滤
- `conversation_repository.py`：会话查询，按 `owner_id` 隔离
- `document_repository.py`：文档元数据查询
- `user_repository.py`：用户查询

#### `app/db/`：SQLAlchemy Base/Session 与 ORM 模型
- `base.py`：`Base = declarative_base()`
- `session.py`：`SessionLocal` 工厂与 `init_db`（含 `_ensure_auth_columns` / `_ensure_collection_name_scope` 兜底）
- `models/collection.py` / `conversation.py` / `document.py` / `message.py` / `user.py`：ORM 模型，均带 `owner_id` 字段（ForeignKey `users.id` ondelete=SET NULL）

#### `app/rag/`：RAG 工具
- `loaders.py`：`load_documents_from_path` 支持 PDF/DOCX/TXT
- `splitters.py`：`split_documents` 使用 `RecursiveCharacterTextSplitter`（默认 `chunk_size=500, overlap=80`）
- `prompts.py`：`build_system_prompt` 注入检索 context
- `retrieval.py`：`reciprocal_rank_fuse` / `rerank_chunk_score` / `compute_keyword_score`

#### `app/vectorstores/`：向量后端
- `base.py`：`VectorStoreBackend` 为 `typing.Protocol`，定义五个方法 `add_documents` / `similarity_search` / `delete_by_document_id` / `keyword_search` / `list_document_chunks`
- `faiss_store.py`：`FAISSVectorStoreBackend`，基于 `langchain_community.vectorstores.FAISS`，索引持久化到 `data/faiss_indexes/{collection_id}/`
- `milvus_store.py`：`MilvusVectorStoreBackend`，使用 `pymilvus`，动态加载符号（`_load_milvus_symbols`），连接 alias 唯一

#### `app/workers/`：Celery app 与 tasks
- `celery_app.py`：创建 Celery 实例，`task_default_queue=document_ingestion`
- `tasks.py`：`ingest_document_task` 实现，从 `self.request.headers` 取 `request_id` 并 `set_context`，调用 `get_ingestion_service()`（lru_cache 单例），`observe_celery_task` 上报指标，`finally reset_context`

#### `app/core/`：基础设施
- `config.py`：`Settings` 类（pydantic-settings），所有配置项集中
- `exceptions.py`：自定义异常与全局异常处理
- `logging.py`：结构化 JSON 日志
- `metrics.py`：Prometheus 指标定义与导出
- `path_utils.py`：路径工具（防越权）
- `request_context.py`：`ContextVar` 封装 request_id（`set_context` / `get_request_id` / `reset_context`）
- `security.py`：手写 JWT（`hash_password` / `verify_password` / `create_access_token` / `decode_access_token`）
- `tracing.py`：OpenTelemetry 初始化

#### `app/frontend/` 与 `app/web/`：前端
- `frontend/static/`：`app.css` / `app.js` / `evaluations.js` / `register.js`
- `frontend/*.html`：`index.html`（聊天）/ `evaluations.html`（评估看板）/ `register.html`（注册）
- `web/router.py`：挂载前端静态资源与页面

### 3.2 依赖方向

```
api  →  services  →  repositories  →  db
                ↓
              rag  →  vectorstores
                ↓
            (LLM/embedding)
api  →  core（config/security/metrics/...）
workers  →  services（复用业务逻辑）
```

关键约束：
- `api` 不直接访问 `repositories`，必须经 `services`
- `services` 不感知 HTTP 细节（不依赖 `Request`/`Response`）
- `workers` 复用 `services`，避免业务逻辑重复
- `vectorstores` 通过 Protocol 抽象，`services` 不感知具体后端

---

## 第四章 核心流程讲解

### 4.1 文档入库流程

入口：`POST /api/v1/documents/upload`（`app/api/v1/documents.py`）→ `DocumentService`（`app/services/document_service.py`）→ `TaskQueueService`（`app/services/task_queue_service.py`）→ Celery → `IngestionService`（`app/services/ingestion_service.py`）。

完整时序：

1. **文件落盘**：用户 `POST /api/v1/documents/upload`，`DocumentService` 调用 `build_document_storage_path`（`app/services/document_service.py`）将文件保存到 `data/raw/`，路径生成遵循 owner_id 与 collection_id 隔离策略，防止越权（`app/core/path_utils.py`）。
2. **元数据落库**：`document_repository.save` 写入 PostgreSQL 元数据，`status="uploaded"`，记录文件名、collection_id、owner_id、size 等。
3. **投递异步任务**：`task_queue_service.enqueue_document_ingestion` 投递 Celery 任务，状态更新为 `status="queued"`，同时通过 `get_request_id()` 取当前 HTTP 请求的 request_id，放入 `apply_async(headers={"request_id": request_id})`。
4. **Worker 执行**：Celery Worker 消费 `document_ingestion` 队列，执行 `ingest_document_task`（`app/workers/tasks.py`）。任务开头从 `self.request.headers` 拿到 `request_id`，调用 `set_context` 注入 ContextVar，使后续日志能关联 HTTP 请求。
5. **加载文档**：`IngestionService.ingest_document` 先将 `status="processing"`，调用 `loaders.load_documents_from_path`（`app/rag/loaders.py`）根据后缀加载 PDF（pypdf）/DOCX（docx2txt）/TXT。
6. **切分**：`splitters.split_documents`（`app/rag/splitters.py`）使用 `RecursiveCharacterTextSplitter`，默认 `chunk_size=500, overlap=80`。
7. **写向量库**：`vector_store_service.add_documents` 写入向量库（FAISS 或 Milvus，由 `settings.vector_backend` 决定）。
8. **状态回写**：成功后 `status="indexed"`，`chunk_count` 回写到 documents 表。
9. **失败路径**：任意步骤抛异常则 `status="failed"`，`error_message` 记录异常信息，`observe_celery_task` 上报 FAILURE 指标。
10. **上下文恢复**：`finally reset_context` 恢复 ContextVar，避免任务间上下文污染。

**文档状态机**（6 态）：

```
uploaded → queued → processing → indexed
                ↘              ↘
                failed          failed
indexed → deleted（软删，向量库已物理删除）
```

### 4.2 聊天问答流程

入口：`POST /api/v1/documents/chat`（`app/api/v1/chat.py`）→ `ChatService.chat`（`app/services/chat_service.py`）。

`chat()` 方法主流程：

1. **校验集合**：校验 `collection` 存在且属于当前 `owner_id`（多租户隔离）。
2. **会话获取/创建**：`get_or_create` conversation，按 `owner_id` 隔离，确保不同用户会话不串。
3. **取历史消息**：`list_messages` 取历史消息，用于上下文构造与 query rewriting。
4. **Query Rewriting**：`_rewrite_query_for_retrieval`（`app/services/chat_service.py`）：
   - 仅当 `use_query_rewrite=True` 且 history 非空才触发
   - 历史窗口：最近 `rag_query_rewrite_history_messages=6` 条
   - SystemMessage 指示 LLM "Return one concise standalone search query only"，**禁止回答**
   - 截断到 `rag_query_rewrite_max_chars=300` 字符
   - try/except 兜底，异常时回退原始 query
5. **混合检索**：`retrieval_service.retrieve`（`app/services/retrieval_service.py`）：
   - Hybrid Search：同时执行 dense（向量）与 keyword（BMVF 风格）召回
   - 候选数扩大为 `top_k * rag_hybrid_candidate_multiplier`（默认 3）
   - RRF 融合：`score = sum(1/(rrf_k + rank))`，默认 `rrf_k=60`（`app/rag/retrieval.py` 的 `reciprocal_rank_fuse`）
   - Rerank：`rerank_chunk_score` 启发式公式（见 5.4）
6. **构造来源**：`_build_sources` 将检索结果构造为 `Source` 列表（含 document_id、chunk_id、source_name、source_path、score、metadata）。
7. **构造 messages**：`_build_messages`：
   - SystemMessage：`build_system_prompt`（`app/rag/prompts.py`）注入检索 context
   - 最近 10 条历史消息
   - 当前 HumanMessage
8. **LLM 调用**：`llm.invoke` 生成回答。
9. **token 用量**：`_extract_token_usage` 从 LLM 响应中提取 prompt_tokens / completion_tokens / total_tokens。
10. **持久化**：将 user message 与 assistant message（含 sources 与 token_usage）写入 messages 表。

### 4.3 SSE 流式输出

入口：`POST /api/v1/documents/chat/stream`（`app/api/v1/chat.py`）→ `ChatService.stream_chat`。

**事件序列**（5 类事件）：

```
start → token（多次）→ sources → done
start → token（部分）→ error（失败时）
```

实现细节：

- `app/api/v1/chat.py` 中 `_encode_sse_event` 生成标准 SSE 格式：`"event: xxx\ndata: {json}\n\n"`
- `StreamingResponse` 设置响应头：
  - `Cache-Control: no-cache`
  - `Connection: keep-alive`
  - `X-Accel-Buffering: no`（防止 Nginx 缓冲，确保流式生效）
- `stream_chat` 是生成器，逐 token yield，前端可中断回答（断开连接即停止 LLM 流式）
- `sources` 事件在 token 流结束后发出，实现"来源延迟回填"——先显示回答正文，再追加来源卡片，体验流畅

### 4.4 异步任务执行

涉及文件：`app/workers/celery_app.py`、`app/workers/tasks.py`、`app/core/request_context.py`、`app/services/task_queue_service.py`。

- **Celery app 创建**：`app/workers/celery_app.py` 创建 Celery 实例，`task_default_queue=document_ingestion`，broker 与 backend 均为 Redis。
- **任务定义**：`ingest_document_task`（`app/workers/tasks.py`）：
  1. 从 `self.request.headers` 拿到 `request_id`
  2. `set_context` 注入 ContextVar（关联 HTTP 请求与异步任务日志）
  3. 调用 `get_ingestion_service()`（`lru_cache` 单例，避免重复初始化 embedding 与 vector store）
  4. 执行 `ingest_document`
  5. `observe_celery_task` 上报 `SUCCESS` / `FAILURE` 指标到 Prometheus
  6. `finally reset_context` 恢复上下文

**上下文透传链路**：

```
HTTP 请求 → FastAPI 中间件 set_context(request_id) 
        → task_queue_service.enqueue_document_ingestion 
        → get_request_id() → apply_async(headers={"request_id": ...})
        → Worker: self.request.headers["request_id"] → set_context
        → 日志带 request_id → finally reset_context
```

这条链路使得 HTTP 请求日志、Celery 任务日志、向量库操作日志可以通过同一个 `request_id` 串联，是项目可观测性的关键基础。

---

## 第五章 关键技术难点（8 个）

### 5.1 自实现 JWT

代码位置：`app/core/security.py`。

项目刻意**不依赖 PyJWT**，手写 JWT 实现：

- **`hash_password`**：使用 `pbkdf2_sha256` 算法，salt 为 16 字节随机（`os.urandom(16)`），迭代次数 390000 次（与 Django 默认一致），存储格式为 `"pbkdf2_sha256${salt}${hash}"`。
- **`verify_password`**：使用 `hmac.compare_digest` 做常量时间比较，**防止时序攻击**（timing attack）。
- **`create_access_token`**：手写 base64url 编码 `header.payload`，HMAC-SHA256 签名，`alg=HS256`，payload 含 `sub`（user_id）与 `exp`（过期时间戳）。
- **`decode_access_token`**：校验签名 + `exp` 过期 + `sub` 存在，任一失败抛对应异常。

**权衡**：
- 优点：减少一个依赖，对 JWT 结构有完全控制，便于教学/面试讲解
- 缺点：维护成本上升（需自己处理 alg=none 攻击、密钥管理、过期边界），生产建议仍用 PyJWT

### 5.2 双向量后端抽象

代码位置：`app/vectorstores/base.py`、`app/services/vector_store_service.py`、`app/vectorstores/faiss_store.py`、`app/vectorstores/milvus_store.py`。

- **`VectorStoreBackend` 为 `typing.Protocol`**，定义五个方法：
  - `add_documents`
  - `similarity_search`
  - `delete_by_document_id`
  - `keyword_search`
  - `list_document_chunks`
- **`VectorStoreService._get_backend` 工厂**：根据 `settings.vector_backend` 选择 `FAISSVectorStoreBackend` 或 `MilvusVectorStoreBackend`。
- **延迟加载**：`_backend` 初始为 `None`，首次调用方法时才创建实例，避免启动时即连接外部依赖。
- **`FAISSVectorStoreBackend`**：基于 `langchain_community.vectorstores.FAISS`，索引持久化到 `data/faiss_indexes/{collection_id}/`，`keyword_search` 遍历 docstore 做关键词匹配。
- **`MilvusVectorStoreBackend`**：使用 `pymilvus`，`_load_milvus_symbols` 动态加载符号（避免未安装时 import 失败），连接 alias 唯一（防重复连接），schema 与维度保护见 5.8。

切换方式：环境变量 `VECTOR_BACKEND=faiss` 或 `VECTOR_BACKEND=milvus`，无需改代码。

### 5.3 Hybrid Search + RRF

代码位置：`app/rag/retrieval.py` 的 `reciprocal_rank_fuse`、`app/services/retrieval_service.py`。

- **Hybrid Search**：同时执行 dense（向量）和 keyword（BMVF 风格）召回，两条通道独立。
- **候选数扩大**：每条通道召回 `top_k * rag_hybrid_candidate_multiplier`（默认 3）条，扩大候选池。
- **RRF 融合**：`reciprocal_rank_fuse` 公式：

  ```
  score = sum(1/(rrf_k + rank))   # 默认 rrf_k=60
  ```

  其中 rank 是文档在某条通道中的排名（从 1 开始）。
- **排序规则**：融合后按 `(fused_score, dense_score, keyword_score)` 三元组排序，确保同分时有一致的回退顺序。
- **元数据记录**：每个 chunk 的 metadata 记录 `retrieval_channels`（命中通道列表）、`dense_rank`、`keyword_score` 等，便于排查与评估。

### 5.4 启发式 Rerank

代码位置：`app/rag/retrieval.py` 的 `rerank_chunk_score` 与 `compute_keyword_score`。

Rerank 公式：

```
score = 0.35*base_score + 0.25*keyword_score + 0.2*coverage + 0.1*phrase_bonus + 0.1*title_bonus
```

各项含义：

- **`base_score`**：检索器原始分数（dense 的相似度或 RRF 融合分）
- **`keyword_score`**：来自 `compute_keyword_score`，公式为 `0.45*coverage + 0.3*density + 0.15*phrase + 0.1*title`
- **`coverage`**：query terms 在 chunk 中的命中比例
- **`phrase_bonus`**：整句命中加成（query 完整子串出现）
- **`title_bonus`**：标题命中加成（source_name 或文档标题包含 query 词）

实现细节：
- 保留 `pre_rerank_score` 到 metadata，便于评估 rerank 的实际增益
- 所有权重为常量，便于调参（但当前未做成配置项，是改进方向之一）

**局限**：启发式公式，非模型 rerank，对语义相关性捕捉有限（见第七章改进 2）。

### 5.5 Query Rewriting

代码位置：`app/services/chat_service.py` 的 `_rewrite_query_for_retrieval`。

- **触发条件**：仅当 `use_query_rewrite=True` 且 history 非空才触发，避免单轮查询浪费 LLM 调用。
- **历史窗口**：取最近 `rag_query_rewrite_history_messages=6` 条消息，避免上下文过长。
- **SystemMessage 约束**：指示 LLM "Return one concise standalone search query only"，**明确禁止回答**用户问题，只做改写。
- **截断保护**：改写结果截断到 `rag_query_rewrite_max_chars=300` 字符，防止 LLM 输出超长。
- **兜底**：try/except 包裹，LLM 调用失败时回退到原始 query，确保主流程不中断。

典型场景：用户先问"公司的报销流程是什么"，再问"需要哪些凭证"。直接检索"需要哪些凭证"会命中大量无关文档，改写为"报销流程需要哪些凭证"后召回显著改善。

### 5.6 Celery 与 FastAPI 上下文透传

代码位置：`app/core/request_context.py`、`app/services/task_queue_service.py`、`app/workers/tasks.py`。

问题：FastAPI 与 Celery 是两个独立进程，ContextVar 不跨进程，异步任务日志无法关联 HTTP 请求。

解决方案：

1. **FastAPI 中间件**：`set_context` 注入 `request_id` 到 ContextVar（`app/core/request_context.py`），并写入 `X-Request-ID` 响应头。
2. **投递任务时透传**：`task_queue_service.enqueue_document_ingestion` 通过 `get_request_id()` 拿到当前 request_id，放入 `apply_async(headers={"request_id": request_id})`。
3. **Worker 端恢复**：`ingest_document_task` 从 `self.request.headers["request_id"]` 拿到 request_id，重新 `set_context` 注入 ContextVar。
4. **finally 清理**：任务结束后 `reset_context` 恢复，避免任务间上下文污染（Celery worker 进程长期运行，ContextVar 不清理会泄漏到下一个任务）。

效果：HTTP 请求日志、Celery 任务日志、向量库操作日志可通过同一个 `request_id` 串联，全链路可追踪。

### 5.7 Alembic bootstrap 兼容旧库

代码位置：`alembic/versions/20260428_01_bootstrap_current_schema.py`、`app/db/session.py` 的 `init_db`。

挑战：项目演进中引入了 `owner_id` 多租户字段，但旧库没有，需要平滑升级。

迁移逻辑：

- **支持两种场景**：全新空库初始化 与 旧库升级
- **旧库缺失 `owner_id` 字段**：`ALTER TABLE ADD COLUMN owner_id VARCHAR(36)`，并建立 ForeignKey 到 `users.id` ondelete=SET NULL
- **唯一约束升级**：`collections` 表的唯一约束从 `name` 升级为 `(owner_id, name)`，即同一用户下集合名唯一，不同用户可重名
- **兜底函数**：`init_db` 中 `_ensure_auth_columns` 与 `_ensure_collection_name_scope` 做运行时兜底，防止迁移未执行时应用启动失败
- **只实现 upgrade**：bootstrap 迁移**无 downgrade**，因为降级会丢失多租户数据
- **生产建议**：`DB_AUTO_INIT=false`，只用 Alembic 管理 schema，避免应用启动时自动建表与迁移冲突

### 5.8 Milvus schema 与维度保护

代码位置：`app/vectorstores/milvus_store.py`。

- **`_ensure_collection`**：若集合已存在，检查 `embedding` 字段的 dim，与当前 embedding 模型维度不匹配时抛 `MILVUS_DIMENSION_MISMATCH` 异常，防止写入失败或检索结果异常。
- **schema 字段**：
  - `id`（VARCHAR，主键）
  - `collection_id`（VARCHAR）
  - `document_id`（VARCHAR）
  - `chunk_id`（VARCHAR）
  - `chunk_index`（INT64）
  - `text`（VARCHAR）
  - `source_name`（VARCHAR）
  - `source_path`（VARCHAR）
  - `metadata_json`（JSON）
  - `embedding`（FLOAT_VECTOR）
  - `created_at`（INT64）
- **索引配置**：`index_type=AUTOINDEX`，`metric_type=COSINE`（默认）
- **`_normalize_score`**：COSINE/IP 距离直接返回 `raw_score`（值越大越相似），其他度量用 `1/(1+score)` 归一化到 `[0,1]`
- **`consistency_level=Strong`**：强一致性，写入立即可读，牺牲部分性能换正确性
- **`_escape` 防注入**：filter 表达式中转义反斜杠与双引号，防止 SQL 注入风格的攻击

---

## 第六章 项目亮点（7 条）

1. **双向量后端无缝切换**：`VectorStoreBackend` Protocol + `VectorStoreService._get_backend` 工厂，`VECTOR_BACKEND=faiss/milvus` 一键切换，业务层无感知（`app/services/vector_store_service.py`）。
2. **三层 RAG 检索增强**：Hybrid Search（dense + keyword）+ RRF 融合 + 启发式 Rerank + Query Rewrite，全套可独立开关，按请求级控制（`app/services/retrieval_service.py` + `app/rag/retrieval.py` + `app/services/chat_service.py` 的 `_rewrite_query_for_retrieval`）。
3. **完整可观测性**：X-Request-ID 透传到 Celery、Prometheus 指标（`/metrics` 端点）、结构化 JSON 日志、可选 OpenTelemetry tracing（`app/core/metrics.py` + `app/core/request_context.py` + `app/core/tracing.py` + `app/core/logging.py`）。
4. **手写 JWT 不依赖 PyJWT**：`pbkdf2_sha256` 密码哈希 + `HMAC-SHA256` 签名，`hmac.compare_digest` 时序攻击防护（`app/core/security.py`）。
5. **多租户 owner_id 隔离**：`collections` / `documents` / `conversations` / `messages` 全部按 `owner_id` 隔离，Alembic bootstrap 兼容旧库迁移（`alembic/versions/20260428_01_bootstrap_current_schema.py` + `app/db/session.py`）。
6. **RAG 评估闭环**：6 项检索指标（Precision@K / Recall@K / HitRate@K / MRR@K / MAP@K / NDCG@K）+ 答案质量（`overall_answer_score` / `groundedness_score` / `grounded_sentence_ratio`）+ 可选 LLM judge（`overall_score` / `groundedness_score` / `relevance_score` / `completeness_score` / `factual_consistency_score`）+ 评估看板前端（`app/services/rag_evaluation_service.py` + `app/frontend/evaluations.html`）。
7. **流式 SSE + 来源延迟回填**：`start` / `token` / `sources` / `done` 事件协议，先流式输出回答正文，再追加来源卡片，前端体验流畅，且可中断回答（`app/services/chat_service.py` 的 `stream_chat` + `app/api/v1/chat.py` 的 `_encode_sse_event`）。

---

## 第七章 项目不足与改进方向（8 条）

1. **已知不足**：仅 access token，无 refresh token 流程（README 明确提到）。
   - **改进**：引入 refresh token + 黑名单（Redis 存已注销的 access token jti），access token 短期（15min），refresh token 长期（7d）。

2. **已知不足**：Rerank 为启发式公式，非模型 rerank。
   - **改进**：接入 `bge-reranker`（本地）或 `cohere rerank`（API），在 `app/rag/retrieval.py` 中新增 `model_rerank` 函数，与启发式 rerank 可切换。

3. **已知不足**：FAISS `keyword_search` 全量遍历 docstore，规模大时性能差。
   - **改进**：引入 BM25 索引（如 `rank_bm25` 库）或迁移到 Milvus 全文检索。

4. **可改进**：删除文档仅 `status=deleted` 软删，但向量库已物理删除，存在一致性窗口。
   - **改进**：统一软删策略（向量库也保留并标记 deleted，检索时过滤），或加事务保证两边一致。

5. **可改进**：Milvus `keyword_search` 也是全量 query 后内存计算 `compute_keyword_score`。
   - **改进**：使用 Milvus 2.4+ 的全文检索能力（scalar index 或 BM25 function），将关键词检索下推到 Milvus。

6. **可改进**：JWT secret 默认值 `"replace-this-secret-key"`，未强制校验。
   - **改进**：启动时校验非默认值，生产环境若仍是默认值则拒绝启动。

7. **可改进**：LLM 调用无熔断/降级，OpenAI 不可用时直接 503。
   - **改进**：引入兜底模型（本地 LLM 或备用 API），加熔断器（如 `pybreaker`），失败时降级为"基于检索结果的模板回答"。

8. **可改进**：测试覆盖 66 passed / 1 skipped，但未做 E2E 与压力测试。
   - **改进**：补 locust 压测脚本（验证 SSE 并发、向量库 QPS），引入 Playwright 做 E2E（覆盖上传 → 入库 → 问答 → 评估全链路）。

---

## 第八章 STAR 故事（3 个）

### STAR 1：RAG 检索增强

- **Situation**：初版 RAG 仅做向量召回，多轮追问时召回不准，专有名词命中差。例如用户问"公司的报销流程"后再问"需要哪些凭证"，直接检索"需要哪些凭证"会命中大量无关文档。
- **Task**：提升召回准确率与多轮对话体验，且每层增强可独立开关。
- **Action**：
  1. 实现 **Hybrid Search**（dense + keyword 双通道召回），候选数扩大为 `top_k * rag_hybrid_candidate_multiplier`（默认 3）
  2. 实现 **RRF 融合**（`app/rag/retrieval.py` 的 `reciprocal_rank_fuse`），公式 `score = sum(1/(60+rank))`
  3. 实现 **启发式 Rerank**（`rerank_chunk_score`），公式 `0.35*base + 0.25*keyword + 0.2*coverage + 0.1*phrase + 0.1*title`
  4. 实现 **Query Rewriting**（`app/services/chat_service.py` 的 `_rewrite_query_for_retrieval`），LLM 改写为独立检索查询，历史窗口 6 条，截断 300 字符，try/except 兜底
  5. 每层增强通过 `use_query_rewrite` / `use_hybrid` / `use_rerank` 等开关控制，可按请求级配置
- **Result**：召回覆盖率提升（用项目自带的 RAG 评估体系验证，6 项检索指标可量化对比），多轮追问能命中正确文档，检索增强可按请求级开关，未开启时回退到基础向量召回。

### STAR 2：用户隔离迁移

- **Situation**：早期 `collections` 全局唯一，无多租户概念，不同用户看到彼此的集合，存在数据泄露风险。
- **Task**：引入 `owner_id` 隔离且兼容旧库，不能丢数据。
- **Action**：
  1. **models 加 `owner_id` 字段**：`ForeignKey users.id ondelete=SET NULL`，所有 ORM 模型（collection / document / conversation / message）统一添加
  2. **仓储层过滤**：`app/repositories/` 下所有查询加 `owner_id` 过滤，确保不串数据
  3. **Alembic bootstrap 迁移**（`alembic/versions/20260428_01_bootstrap_current_schema.py`）：`ALTER TABLE ADD COLUMN owner_id VARCHAR(36)` + 升级唯一约束为 `(owner_id, name)`
  4. **`init_db` 兜底**：`_ensure_auth_columns` 与 `_ensure_collection_name_scope` 做运行时兜底，防止迁移未执行时应用启动失败
  5. **bootstrap 只实现 upgrade**：无 downgrade，因为降级会丢失多租户数据
- **Result**：多用户数据隔离上线，旧库平滑升级无数据丢失。README 明确"缺失 owner_id 仍需手工回填"，对历史数据做了诚实披露。

### STAR 3：异步入库与可观测性

- **Situation**：文档入库耗时长（PDF 解析 + 切分 + embedding + 写向量库），同步阻塞 API 导致请求超时；线上问题难定位（HTTP 与 Celery 日志无法关联）。
- **Task**：异步入库 + 全链路可观测，入库失败可追踪。
- **Action**：
  1. **Celery + Redis 异步队列**：`task_default_queue=document_ingestion`，文档上传后立即返回，Worker 异步处理
  2. **request_id 透传**：`TaskQueueService.enqueue_document_ingestion` 通过 `get_request_id()` 取当前 HTTP 请求的 request_id，放入 `apply_async(headers={"request_id": request_id})`，Worker 端 `set_context` 注入 ContextVar
  3. **结构化 JSON 日志**：`app/core/logging.py` 输出 JSON 格式，含 timestamp / level / request_id / message / extra
  4. **Prometheus 指标**：`app/core/metrics.py` 定义 `chatrobot_http_requests_total` / `chatrobot_celery_tasks_total` 等，`/metrics` 端点导出
  5. **X-Request-ID 响应头**：FastAPI 中间件写入，用户可凭此 ID 查日志
  6. **OpenTelemetry tracing**：自动埋点 FastAPI / Celery / SQLAlchemy，span 关联 request_id
- **Result**：API 响应快（上传即返回，不入库阻塞），入库失败可追踪（request_id 串联全链路日志），HTTP / Celery 日志可关联。线上排查问题从"看一堆日志"变成"按 request_id 过滤"。

---

## 第九章 可量化结果

- **测试**：66 passed / 1 skipped（README 最近一次完整验证）
- **向量后端**：FAISS + Milvus 双后端，`VECTOR_BACKEND` 一键切换
- **RAG 检索**：3 层增强（Hybrid / RRF / Rerank）+ Query Rewrite，每层独立开关
- **评估指标**：
  - 检索：6 项（Precision@K / Recall@K / HitRate@K / MRR@K / MAP@K / NDCG@K）
  - 答案质量：`overall_answer_score` / `groundedness_score` / `grounded_sentence_ratio`
  - LLM judge（可选）：`overall_score` / `groundedness_score` / `relevance_score` / `completeness_score` / `factual_consistency_score`
- **文档状态机**：uploaded / queued / processing / indexed / failed / deleted 共 6 态
- **SSE 事件**：start / token / sources / done / error 共 5 类
- **资源隔离**：4 类资源（collections / documents / conversations / messages）按 `owner_id` 隔离
- **可观测性**：3 大支柱（Metrics / Logging / Tracing）+ Request ID 透传

---

## 第十章 面试官视角提问清单

按 11 个主题分类，每个主题至少 3 个问题（简单 / 中等 / 深挖三档），每个问题包含「考察点」+「参考答案要点（对应代码位置）」。

### 主题 1：架构与分层

**Q1（简单）：项目分了哪些层？依赖方向是怎样的？**
- 考察点：对整体架构的掌握
- 参考答案要点：
  1. 分层：`api/v1` → `services` → `repositories` → `db`；`services` → `rag` → `vectorstores`；`api` → `core`；`workers` 复用 `services`（`app/api/v1/router.py` 聚合路由）
  2. 依赖单向：api 不直接访问 repositories，必须经 services；services 不感知 HTTP 细节
  3. workers 复用 services，避免业务逻辑重复

**Q2（中等）：为什么 `VectorStoreBackend` 用 Protocol 而不是抽象基类（ABC）？**
- 考察点：Python 类型系统与设计模式理解
- 参考答案要点：
  1. Protocol 是结构性子类型（鸭子类型 + 静态检查），FAISS/Milvus 后端无需显式继承即可被识别（`app/vectorstores/base.py`）
  2. ABC 是名义子类型，需显式继承，对第三方类（如 langchain_community.FAISS 包装）侵入性更大
  3. Protocol 更适合"定义能力契约"场景，配合工厂模式（`VectorStoreService._get_backend`）实现无缝切换

**Q3（深挖）：如果要把 `chat_service` 从同步 `llm.invoke` 改成异步 `llm.ainvoke`，需要改哪些地方？FastAPI 的同步路由与异步路由在数据库操作上有什么坑？**
- 考察点：异步改造的影响范围与 FastAPI 同步/异步混合的陷阱
- 参考答案要点：
  1. `chat_service.chat` 与 `stream_chat` 内 `llm.invoke` → `await llm.ainvoke`，整个方法需 `async def`（`app/services/chat_service.py`）
  2. `retrieval_service.retrieve` 若内部有 IO 也需异步化
  3. SQLAlchemy 同步 Session 在 async 路由中会阻塞事件循环，需换 `async_session` 或用 `run_in_threadpool`
  4. SSE 的 `StreamingResponse` 接受异步生成器，改造后更自然
  5. Celery 任务仍是同步，异步化收益主要在 HTTP 层并发

### 主题 2：RAG 检索（Hybrid / RRF / Rerank / Query Rewrite）

**Q4（简单）：RRF 融合的公式是什么？为什么用 1/(k+rank) 而不是直接加分数？**
- 考察点：RRF 原理理解
- 参考答案要点：
  1. 公式：`score = sum(1/(rrf_k + rank))`，默认 `rrf_k=60`（`app/rag/retrieval.py` 的 `reciprocal_rank_fuse`）
  2. 不同检索器的分数尺度不同（向量相似度 0~1，BM25 可能 0~30），直接相加会被高分尺度主导
  3. 用 rank 而非 score，尺度无关，且对异常值鲁棒
  4. k=60 是经验值，控制排名靠后项的衰减速度

**Q5（中等）：Rerank 的 5 个权重（0.35/0.25/0.2/0.1/0.1）是怎么定的？如何验证它的效果？**
- 考察点：Rerank 设计与评估闭环
- 参考答案要点：
  1. 权重为人工经验设定，`base_score` 占主导（0.35），`keyword_score` 次之（0.25），`coverage`（0.2）保证 query 命中，`phrase_bonus` 与 `title_bonus` 各 0.1（`app/rag/retrieval.py` 的 `rerank_chunk_score`）
  2. 验证方式：用项目自带的 RAG 评估体系（`app/services/rag_evaluation_service.py`），对比开启/关闭 rerank 时的 Precision@K / Recall@K / NDCG@K
  3. 保留 `pre_rerank_score` 到 metadata，可单独分析 rerank 的增益
  4. 局限：未做网格搜索或学习排序，是改进方向

**Q6（深挖）：Query Rewriting 失败时回退到原始 query，但如果 LLM 返回了"我不确定"这类非改写内容，会发生什么？如何防御？**
- 考察点：异常处理与 LLM 输出鲁棒性
- 参考答案要点：
  1. 当前实现：try/except 包裹，异常时回退原始 query（`app/services/chat_service.py` 的 `_rewrite_query_for_retrieval`）
  2. 风险：LLM 返回非 query 文本（如"我不确定"）时不会抛异常，会被当作 query 检索，导致召回垃圾
  3. 防御：截断到 `rag_query_rewrite_max_chars=300` 减少影响，但未做内容校验
  4. 改进：加正则或二次 LLM 校验"是否为合法检索 query"，或限制输出长度+去标点

### 主题 3：向量后端（FAISS / Milvus）

**Q7（简单）：FAISS 后端的索引持久化在哪里？多 collection 如何隔离？**
- 考察点：FAISS 工程实践
- 参考答案要点：
  1. 持久化路径：`data/faiss_indexes/{collection_id}/`（`app/vectorstores/faiss_store.py`）
  2. 每个 collection 一个独立目录，含 `index.faiss` 与 `index.pkl`（docstore）
  3. 加载时按 collection_id 路径加载，自然隔离
  4. `delete_by_document_id` 需重建索引（FAISS 不支持原地删除）

**Q8（中等）：Milvus 的 `_ensure_collection` 如何防止维度不匹配？换 embedding 模型时会发生什么？**
- 考察点：Milvus schema 与运维
- 参考答案要点：
  1. `_ensure_collection` 检查已存在集合的 `embedding` 字段 dim，不匹配抛 `MILVUS_DIMENSION_MISMATCH`（`app/vectorstores/milvus_store.py`）
  2. 换 embedding 模型（如 1536 维 → 768 维）时，旧集合维度不匹配，写入/检索都会失败
  3. 正确做法：新建 collection（新维度），重新入库全部文档，删除旧 collection
  4. 项目未做自动迁移，需手动操作

**Q9（深挖）：FAISS 的 `keyword_search` 全量遍历 docstore，假设一个 collection 有 100 万 chunk，单次 keyword_search 要多久？如何优化？**
- 考察点：性能分析与优化方向
- 参考答案要点：
  1. 全量遍历：每个 chunk 做字符串匹配，100 万 chunk 单次约秒级（取决于文本长度与 CPU）
  2. 优化方向 1：引入 BM25 索引（`rank_bm25` 库），O(log N) 查询
  3. 优化方向 2：迁移到 Milvus 2.4+ 全文检索（scalar index 或 BM25 function）
  4. 优化方向 3：对 keyword 结果做缓存（Redis，query hash 为 key）
  5. 当前实现的合理性：小规模知识库（<1万 chunk）够用，大规模需优化

### 主题 4：异步任务（Celery + Redis）

**Q10（简单）：为什么文档入库要异步化？同步会有什么问题？**
- 考察点：异步化动机
- 参考答案要点：
  1. 入库耗时长：PDF 解析 + 切分 + embedding 调用 + 写向量库，单文档可能 10s+
  2. 同步阻塞 API：HTTP 请求超时，FastAPI worker 被占满，影响其他请求
  3. 异步化后上传立即返回 `status="queued"`，Worker 异步处理，状态机驱动前端刷新
  4. Celery 还提供重试、并发控制、任务追踪等能力

**Q11（中等）：`ingest_document_task` 为什么用 `lru_cache` 单例 `get_ingestion_service`？每次新建有什么问题？**
- 考察点：Celery worker 生命周期与资源管理
- 参考答案要点：
  1. Celery worker 是长驻进程，一个 worker 处理多个任务（`app/workers/tasks.py`）
  2. `IngestionService` 持有 embedding 客户端、vector store 后端等重资源，每次新建会导致重复初始化（embedding 模型加载、Milvus 连接建立）
  3. `lru_cache` 单例复用这些资源，提升吞吐
  4. 副作用：单例持有状态需注意线程安全（Celery prefork 模式下每个 worker 进程独立，无并发问题；gevent/eventlet 需注意）

**Q12（深挖）：如果文档入库失败，状态停在 `failed`，如何重试？重试时如何避免重复写入向量库？**
- 考察点：幂等性与重试设计
- 参考答案要点：
  1. 当前实现：`status="failed"` + `error_message` 记录，需手动重新上传或调用重试接口
  2. 重试风险：若已部分写入向量库，重试会重复写入
  3. 幂等设计：重试前先 `delete_by_document_id` 清理旧 chunk，再重新入库
  4. 改进：任务级幂等键（document_id + version），向量库写入前检查是否已存在
  5. Celery 原生 `autoretry_for` 可自动重试，但需配合幂等

### 主题 5：鉴权与数据隔离

**Q13（简单）：JWT 是怎么生成的？为什么不用 PyJWT？**
- 考察点：JWT 实现细节
- 参考答案要点：
  1. `create_access_token`：手写 base64url 编码 `header.payload`，HMAC-SHA256 签名，`alg=HS256`（`app/core/security.py`）
  2. payload 含 `sub`（user_id）与 `exp`（过期时间戳）
  3. 不用 PyJWT 的原因：减少依赖，对 JWT 结构有完全控制，便于教学/面试讲解
  4. 代价：需自己处理 alg=none 攻击、密钥管理、过期边界，维护成本高

**Q14（中等）：`verify_password` 为什么用 `hmac.compare_digest` 而不是 `==`？**
- 考察点：时序攻击防护
- 参考答案要点：
  1. `==` 在字符不同时提前返回，攻击者可通过响应时间推断正确字符数（时序攻击）
  2. `hmac.compare_digest` 常量时间比较，无论哪里不同都遍历完整个字符串（`app/core/security.py`）
  3. 适用于密码哈希比较、HMAC 签名校验等场景
  4. 注意：只能用于等长字符串比较，长度不同时仍会提前返回

**Q15（深挖）：owner_id 隔离在仓储层是怎么实现的？如果有 100 万用户，每个用户 1000 文档，查询性能如何？如何优化？**
- 考察点：多租户隔离与性能
- 参考答案要点：
  1. 仓储层所有查询加 `WHERE owner_id = :owner_id` 过滤（`app/repositories/collection_repository.py` 等）
  2. 索引：`owner_id` 字段加索引，`(owner_id, collection_id)` 复合索引加速关联查询
  3. 100 万用户 × 1000 文档 = 10 亿行，单表撑不住，需分库分表（按 owner_id hash 分片）
  4. 或行级安全（PostgreSQL RLS），让数据库强制隔离，应用层无需手动加 WHERE
  5. 当前实现适合中小规模（<1000 万行），超大规模需重构

### 主题 6：数据库迁移（Alembic）

**Q16（简单）：为什么 bootstrap 迁移只有 upgrade 没有 downgrade？**
- 考察点：迁移设计原则
- 参考答案要点：
  1. bootstrap 引入了 `owner_id` 字段与 `(owner_id, name)` 唯一约束（`alembic/versions/20260428_01_bootstrap_current_schema.py`）
  2. downgrade 会删除 `owner_id`，丢失多租户数据关联，不可逆
  3. 设计原则：破坏性变更不做 downgrade，回滚靠备份
  4. 生产建议：`DB_AUTO_INIT=false`，只用 Alembic，迁移前先备份

**Q17（中等）：`init_db` 里的 `_ensure_auth_columns` 和 `_ensure_collection_name_scope` 是干什么的？为什么需要它们？**
- 考察点：运行时兜底与迁移的关系
- 参考答案要点：
  1. 作用：`_ensure_auth_columns` 确保 users 表有必需字段，`_ensure_collection_name_scope` 确保 collections 唯一约束是 `(owner_id, name)`（`app/db/session.py`）
  2. 必要性：Alembic 迁移可能未执行（开发环境直接启动），兜底保证应用能跑
  3. 与 Alembic 的关系：Alembic 是权威，兜底是防御性编程
  4. 风险：兜底逻辑与迁移逻辑重复，维护成本高，生产应禁用 `DB_AUTO_INIT`

**Q18（深挖）：旧库升级时，如果 `collections` 表已有重复的 `name`（不同用户同名集合），升级唯一约束为 `(owner_id, name)` 会失败吗？如何处理？**
- 考察点：迁移的边界情况
- 参考答案要点：
  1. 不会失败：旧库 `owner_id` 为 NULL，`(NULL, name)` 在 PostgreSQL 中视为不同值（NULL 不参与唯一约束），不会冲突
  2. 但语义上有问题：旧数据 owner_id 为 NULL，无法归属用户
  3. 处理：迁移后手动回填 owner_id（如分配给管理员），README 明确"缺失 owner_id 仍需手工回填"
  4. 若 MySQL（NULL 参与唯一约束），需先去重再升级

### 主题 7：可观测性（Metrics / Logging / Tracing / Request ID）

**Q19（简单）：X-Request-ID 是怎么从 HTTP 请求传到 Celery 任务日志的？**
- 考察点：上下文透传链路
- 参考答案要点：
  1. FastAPI 中间件 `set_context` 注入 request_id 到 ContextVar（`app/core/request_context.py`）
  2. `task_queue_service.enqueue_document_ingestion` 通过 `get_request_id()` 取出，放入 `apply_async(headers={"request_id": ...})`
  3. Worker 端 `ingest_document_task` 从 `self.request.headers["request_id"]` 拿到，重新 `set_context`
  4. 日志格式器从 ContextVar 读 request_id 输出到每条日志，实现关联

**Q20（中等）：Prometheus 指标有哪些？如何区分 HTTP 与 Celery 的指标？**
- 考察点：指标设计
- 参考答案要点：
  1. HTTP：`chatrobot_http_requests_total`（label: method/path/status）（`app/core/metrics.py`）
  2. Celery：`chatrobot_celery_tasks_total`（label: task_name/status），通过 `observe_celery_task` 上报
  3. 区分方式：不同指标名 + label，Grafana 可按 label 筛选
  4. 导出：`/metrics` 端点（FastAPI 路由），Prometheus pull 拉取

**Q21（深挖）：ContextVar 在 Celery prefork 模式下安全吗？在 gevent 模式下呢？为什么 `finally reset_context` 是必要的？**
- 考察点：并发模型与上下文管理
- 参考答案要点：
  1. prefork 模式：每个 worker 是独立进程，进程内单任务串行，ContextVar 安全
  2. gevent/eventlet 模式：协程共享进程，ContextVar 是协程局部，gevent 打补丁后仍安全（ContextVar 支持协程）
  3. `finally reset_context` 必要性：worker 进程长期运行，ContextVar 不清理会泄漏到下一个任务（如 task A 的 request_id 被记到 task B 日志）
  4. 类比：线程池中 ThreadLocal 不清理的同类问题

### 主题 8：RAG 评估体系

**Q22（简单）：RAG 评估有哪些指标？Precision@K 和 Recall@K 的区别是什么？**
- 考察点：评估指标基础
- 参考答案要点：
  1. 检索指标 6 项：Precision@K / Recall@K / HitRate@K / MRR@K / MAP@K / NDCG@K（`app/services/rag_evaluation_service.py`）
  2. Precision@K：前 K 个结果中相关项的比例（准不准）
  3. Recall@K：前 K 个结果覆盖所有相关项的比例（全不全）
  4. 区别：Precision 关注返回结果的纯度，Recall 关注相关项是否被找到，二者常需权衡
  5. 答案质量：`overall_answer_score` / `groundedness_score` / `grounded_sentence_ratio`

**Q23（中等）：NDCG@K 和 MRR@K 有什么区别？什么场景下 NDCG 比 MRR 更合适？**
- 考察点：排序质量指标
- 参考答案要点：
  1. MRR@K：第一个相关结果的位置倒数，只关心第一个命中（1/rank）
  2. NDCG@K：考虑所有相关结果的位置，越靠前分越高，并做归一化（DCG/IDCG）
  3. 区别：MRR 只看第一个命中，NDCG 看整体排序质量
  4. NDCG 更合适的场景：需要多个相关结果（如"列出所有报销凭证"），或相关度有分级（完全相关 > 部分相关）

**Q24（深挖）：LLM judge 是怎么实现的？如何保证 judge 的评分一致性？**
- 考察点：LLM 评估的可信度
- 参考答案要点：
  1. 实现：调用 LLM 对 (query, answer, contexts, ground_truth) 评分，输出 `overall_score` / `groundedness_score` / `relevance_score` / `completeness_score` / `factual_consistency_score`（`app/services/rag_evaluation_service.py`）
  2. 一致性问题：LLM 评分随机性大，同一输入可能不同分
  3. 缓解：temperature=0、few-shot 示例、多次评分取均值、与人工标注对齐校准
  4. 局限：LLM judge 本身可能幻觉，不能完全替代人工评估
  5. 项目中是可选项，默认关闭

### 主题 9：流式输出（SSE）

**Q25（简单）：SSE 的事件序列是什么？为什么 sources 在 token 之后？**
- 考察点：SSE 协议设计
- 参考答案要点：
  1. 事件序列：`start → token（多次）→ sources → done`（`app/services/chat_service.py` 的 `stream_chat`）
  2. sources 在 token 之后：先流式输出回答正文，让用户立即看到内容；回答结束后再追加来源卡片
  3. 体验：避免等待全部生成完才显示，提升首字响应速度
  4. 失败序列：`start → token（部分）→ error`

**Q26（中等）：`X-Accel-Buffering: no` 这个响应头是干什么的？不加会怎样？**
- 考察点：SSE 在反向代理下的坑
- 参考答案要点：
  1. 作用：禁止 Nginx 缓冲响应，让 SSE 立即透传到客户端（`app/api/v1/chat.py`）
  2. 不加：Nginx 默认缓冲响应，SSE 事件会攒在 Nginx 缓冲区，客户端收不到实时流
  3. 类似：`Cache-Control: no-cache` 防止中间代理缓存
  4. 其他反向代理（如 Cloudflare）也有类似配置

**Q27（深挖）：前端中断 SSE 后，后端的 LLM 调用会自动停止吗？如何实现真正的"可中断"？**
- 考察点：SSE 中断的底层机制
- 参考答案要点：
  1. 前端断开连接后，FastAPI 的 `StreamingResponse` 生成器会在下次 yield 时检测到客户端断开，抛 `ClientDisconnect`
  2. 但 LLM 调用（`llm.invoke` 或 `llm.stream`）不会自动停止，仍会继续生成
  3. 真正可中断：用 `llm.stream` 逐 token 生成，每次 yield 后检查 `request.is_disconnected()`，断开则 break
  4. OpenAI API 支持 `stream=True` + 主动 abort 请求（关闭底层 httpx 连接）
  5. 当前实现：部分可中断（生成器层面），但 LLM API 调用可能继续计费

### 主题 10：测试与工程质量

**Q28（简单）：项目测试覆盖了哪些模块？测试是怎么跑的？**
- 考察点：测试体系
- 参考答案要点：
  1. 覆盖：`tests/` 下 17 个测试文件，覆盖 auth/chat/collection/conversation/document/health/rag_evaluation/retrieval/vector_store/web 等模块
  2. 工具：pytest + httpx（TestClient）
  3. 结果：66 passed / 1 skipped（README 最近一次完整验证）
  4. skipped 原因：通常是依赖外部服务（如 Milvus 集成测试 `test_milvus_integration.py`）

**Q29（中等）：如何测试 SSE 流式接口？httpx 的 TestClient 支持流式吗？**
- 考察点：流式接口测试
- 参考答案要点：
  1. httpx 的 TestClient 支持流式响应，可逐行读取 SSE 事件
  2. 测试方式：发送请求，读取响应流，按 `event: xxx\ndata: {json}\n\n` 解析
  3. 断言：事件序列正确（start → token → sources → done）、token 内容非空、sources 结构正确
  4. 难点：流式响应不能直接用 `response.json()`，需手动解析

**Q30（深挖）：项目没有 E2E 测试和压力测试，如果要补，你会怎么设计？**
- 考察点：测试体系完善
- 参考答案要点：
  1. E2E：Playwright 覆盖"注册 → 登录 → 上传文档 → 等待入库 → 提问 → 查看来源 → 查看评估"全链路
  2. 压测：Locust 模拟并发用户，验证 SSE 并发稳定性、向量库 QPS、Celery worker 吞吐
  3. 关键场景：100 用户同时 SSE 流式问答、10 个文档并发入库、Milvus 检索 P99 延迟
  4. 指标：P50/P99 响应时间、错误率、资源占用（CPU/内存/连接数）
  5. 集成到 CI：夜跑 E2E，发布前压测

### 主题 11：运维与生产部署

**Q31（简单）：项目是怎么部署的？用了哪些容器化技术？**
- 考察点：部署方式
- 参考答案要点：
  1. 容器化：`Dockerfile` + `docker-compose.yml`
  2. docker-compose 编排：FastAPI（web）+ Celery worker + Redis + PostgreSQL + Milvus（可选）
  3. 配置：`.env.example` 列出所有环境变量
  4. 数据卷：`data/` 目录挂载（raw 文档、faiss 索引、evals 报告）

**Q32（中等）：生产环境如何平滑升级（不丢请求、不丢数据）？**
- 考察点：滚动升级
- 参考答案要点：
  1. 多实例：FastAPI 多实例 + 负载均衡（Nginx/ALB），逐个滚动升级
  2. Celery worker：`celery multi restart` 或 k8s 滚动升级，旧任务执行完再退出（`--without-gossip` + 优雅关闭）
  3. 数据库：Alembic 迁移先于应用升级，迁移需向后兼容（不加列、不改列类型，先加新列后删旧列）
  4. 向量库：FAISS 索引文件持久化，升级不丢；Milvus 独立部署，与应用升级解耦
  5. SSE 长连接：升级时旧连接断开，前端需重连（EventSource 自动重连）

**Q33（深挖）：JWT secret 默认值是 "replace-this-secret-key"，生产环境如何安全管理密钥？**
- 考察点：密钥管理
- 参考答案要点：
  1. 当前问题：默认值未强制校验，误用会导致 token 可伪造（`app/core/config.py`）
  2. 改进 1：启动时校验非默认值，生产环境若是默认值则拒绝启动
  3. 改进 2：密钥从密钥管理服务（如 AWS Secrets Manager / HashiCorp Vault）动态拉取，不落盘
  4. 改进 3：密钥轮转（双密钥共存期 + 旧密钥失效），secret 版本化
  5. 改进 4：审计密钥访问日志，异常访问告警
  6. 当前实现适合开发，生产需补强

---

## 附录：关键文件路径速查

| 模块 | 路径 |
| --- | --- |
| FastAPI 入口 | `app/main.py` |
| 路由聚合 | `app/api/v1/router.py` |
| 聊天服务 | `app/services/chat_service.py` |
| 入库服务 | `app/services/ingestion_service.py` |
| 检索服务 | `app/services/retrieval_service.py` |
| 向量后端工厂 | `app/services/vector_store_service.py` |
| 向量后端抽象 | `app/vectorstores/base.py` |
| FAISS 后端 | `app/vectorstores/faiss_store.py` |
| Milvus 后端 | `app/vectorstores/milvus_store.py` |
| RAG 检索工具 | `app/rag/retrieval.py` |
| RAG 文档加载 | `app/rag/loaders.py` |
| RAG 文本切分 | `app/rag/splitters.py` |
| RAG 提示词 | `app/rag/prompts.py` |
| JWT 实现 | `app/core/security.py` |
| 配置管理 | `app/core/config.py` |
| 请求上下文 | `app/core/request_context.py` |
| 指标 | `app/core/metrics.py` |
| 日志 | `app/core/logging.py` |
| Tracing | `app/core/tracing.py` |
| Celery app | `app/workers/celery_app.py` |
| Celery 任务 | `app/workers/tasks.py` |
| 任务队列服务 | `app/services/task_queue_service.py` |
| ORM 模型 | `app/db/models/` |
| 数据库 session | `app/db/session.py` |
| Alembic bootstrap | `alembic/versions/20260428_01_bootstrap_current_schema.py` |
| RAG 评估服务 | `app/services/rag_evaluation_service.py` |
| RAG 评估报告 | `app/services/rag_evaluation_report_service.py` |
| 评估看板前端 | `app/frontend/evaluations.html` |

---

## 附录：关键配置项速查

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `VECTOR_BACKEND` | `faiss` | 向量后端，可选 `faiss` / `milvus` |
| `CHUNK_SIZE` | 500 | 文本切分 chunk 大小 |
| `CHUNK_OVERLAP` | 80 | 文本切分重叠 |
| `RAG_HYBRID_CANDIDATE_MULTIPLIER` | 3 | Hybrid 候选数扩大倍数 |
| `RRF_K` | 60 | RRF 融合参数 |
| `RAG_QUERY_REWRITE_HISTORY_MESSAGES` | 6 | Query Rewriting 历史窗口 |
| `RAG_QUERY_REWRITE_MAX_CHARS` | 300 | Query Rewriting 截断字符数 |
| `DB_AUTO_INIT` | true | 是否启动时自动建表（生产建议 false） |
| JWT secret | `replace-this-secret-key` | 默认值，生产必须替换 |
| Celery `task_default_queue` | `document_ingestion` | 默认任务队列 |

---

> 本文档基于 `d:\Dify\LangChain\ChatRobot_v3` 仓库真实代码撰写，所有文件路径、函数名、配置项均可在仓库中直接核对。面试讲述时建议结合具体代码位置展开，体现对项目的深度掌握。
