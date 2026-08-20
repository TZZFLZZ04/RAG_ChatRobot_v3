# AGENTS.md — AI 协作上下文文档

本文档为后续 AI Agent（如 Claude Code）协作提供项目全景、技术栈、目录结构、常用命令和代码规范。修改项目前请先阅读本文件。

---

## 1. 项目简介

**ChatRobot_v3** 是一个面向企业知识问答场景的 **RAG（Retrieval-Augmented Generation）应用**。项目已从最初的单文件 LangChain CLI Demo（`ChatRobot_v3.0.py`）演进为前后端一体化的 FastAPI 工程，目标是为团队提供可私有化部署、可评估、可观测的知识库问答系统。

当前核心能力：

- JWT 用户注册、登录与受保护 API，数据按用户隔离。
- 知识库（Collection）、文档（Document）、会话（Conversation）、消息（Message）的完整 CRUD。
- 多文件上传与 Celery + Redis 异步文档入库流程。
- 可切换的 FAISS / Milvus 双向量后端。
- FastAPI 后端 + 原生 HTML/CSS/JavaScript 前端，无 npm 构建步骤。
- `POST /api/v1/chat/completions` 支持普通 JSON 响应与 `stream=true` 的 SSE 流式输出。
- 三层检索增强：Hybrid Search（向量 + 关键词 + RRF）、Reranking、Query Rewriting。
- 完整 RAG 评估体系：JSON / JSONL 数据集、检索指标、答案质量、Groundedness、Source Match、Latency、Token Usage、可选 LLM Judge。
- 评估报告看板：后端 API + 前端 `/evaluations` 页面，可运行评估、查看历史报告。
- 可观测性：结构化 JSON 日志、Request ID 中间件、API Latency 日志、Celery Task 日志、Prometheus `/metrics`、OpenTelemetry Tracing 接入点。

当前前端页面包括：登录/注册、知识库管理、文档上传与状态、文档详情与分块预览、会话历史、聊天工作台、评估看板。

---

## 2. 技术栈和版本

项目是 **Python 3.11** 的 FastAPI 应用。前端为原生 HTML/CSS/JS，没有 Node.js/npm 构建步骤。

> 注意：`requirements.txt` 当前没有 pin 固定版本，下面版本来自本地当前环境，仅作为协作参考，不代表锁定版本。

### 运行时与语言

- Python: `3.11.7`
- Docker base image: `python:3.11-slim`

### Web 框架

- FastAPI: `0.115.0`
- Uvicorn: `0.31.0`（`uvicorn[standard]`）
- Pydantic: `2.9.2`
- pydantic-settings: 读取 `.env` 配置

### 数据库与 ORM

- SQLAlchemy: `2.0.35`
- Alembic: `1.18.4`
- psycopg2-binary: PostgreSQL 驱动
- PostgreSQL Docker image: `postgres:16`

### 任务队列与缓存

- Celery: `5.6.3`
- Redis Docker image: `redis:7`

### LLM / RAG / 向量

- LangChain: `0.3.1`
- langchain-openai: `0.2.1`
- langchain-community / langchain-text-splitters
- OpenAI Python SDK: `1.50.2`
- FAISS-CPU: `1.8.0.post1`
- PyMilvus: `2.6.12`
- Milvus Docker image: `milvusdb/milvus:v2.5.10`

### 文档解析

- pypdf
- docx2txt

### 可观测性

- prometheus-client
- opentelemetry-api / opentelemetry-sdk / opentelemetry-exporter-otlp-proto-http
- OpenTelemetry instrumentation: FastAPI、Celery、SQLAlchemy

### 测试

- pytest: `9.0.3`
- httpx: `0.27.2`

### 前端

- 原生 HTML / CSS / JavaScript
- 无 npm、无 bundler
- 语法检查可用 `node --check`

---

## 3. 目录结构说明

```text
D:/Dify/LangChain/ChatRobot_v3/
├── app/                          # 主应用包
│   ├── api/                      # FastAPI 路由与依赖
│   │   ├── deps.py               # 依赖工厂 / service 单例
│   │   └── v1/                   # API v1 路由
│   │       ├── auth.py
│   │       ├── chat.py
│   │       ├── collections.py
│   │       ├── conversations.py
│   │       ├── documents.py
│   │       ├── health.py
│   │       ├── rag_evaluations.py
│   │       └── router.py         # 聚合所有 v1 路由
│   ├── core/                     # 配置、安全、日志、metrics、tracing、异常
│   │   ├── config.py             # pydantic-settings 环境配置
│   │   ├── security.py           # JWT / 密码哈希
│   │   ├── logging.py            # 结构化 JSON 日志
│   │   ├── metrics.py            # Prometheus 指标
│   │   ├── tracing.py            # OpenTelemetry 初始化
│   │   ├── request_context.py    # Request ID / 关联上下文
│   │   ├── exceptions.py         # 自定义异常与处理器
│   │   └── path_utils.py         # 数据路径工具
│   ├── db/                       # SQLAlchemy ORM
│   │   ├── base.py               # Declarative Base
│   │   ├── session.py            # Engine / Session 工厂
│   │   └── models/               # User, Collection, Document, Conversation, Message
│   ├── frontend/                 # 静态 HTML/CSS/JS 前端
│   │   ├── index.html
│   │   ├── register.html
│   │   ├── evaluations.html
│   │   └── static/
│   │       ├── app.css
│   │       ├── app.js            # 主聊天 / 工作台 UI
│   │       ├── register.js
│   │       └── evaluations.js    # 评估看板
│   ├── rag/                      # RAG 基础能力
│   │   ├── loaders.py            # PDF/DOCX/TXT 加载器
│   │   ├── splitters.py          # 文本切分
│   │   ├── prompts.py            # LLM Prompt
│   │   └── retrieval.py          # 检索评分辅助
│   ├── repositories/             # 数据访问层
│   │   ├── base.py
│   │   ├── user_repository.py
│   │   ├── collection_repository.py
│   │   ├── document_repository.py
│   │   └── conversation_repository.py
│   ├── schemas/                  # Pydantic 请求/响应/评估 schema
│   │   ├── auth.py
│   │   ├── chat.py
│   │   ├── collection.py
│   │   ├── document.py
│   │   └── rag_eval.py
│   ├── services/                 # 业务逻辑
│   │   ├── user_service.py
│   │   ├── collection_service.py
│   │   ├── document_service.py
│   │   ├── ingestion_service.py
│   │   ├── chat_service.py
│   │   ├── conversation_service.py
│   │   ├── retrieval_service.py
│   │   ├── embedding_service.py
│   │   ├── vector_store_service.py
│   │   ├── rag_evaluation_service.py
│   │   └── rag_evaluation_report_service.py
│   ├── vectorstores/             # FAISS / Milvus 实现
│   │   ├── base.py
│   │   ├── faiss_store.py
│   │   └── milvus_store.py
│   ├── web/                      # 页面路由
│   │   └── router.py
│   ├── workers/                  # Celery 配置与任务
│   │   ├── celery_app.py
│   │   └── tasks.py
│   └── main.py                   # FastAPI app factory、生命周期、中间件
├── alembic/                      # 数据库迁移
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── 20260428_01_bootstrap_current_schema.py
├── data/                         # 运行时数据
│   ├── raw/                      # 原始上传文档
│   ├── processed/                # 处理后元数据
│   ├── faiss_indexes/            # FAISS 索引文件
│   └── evals/                    # 评估数据集与报告
│       ├── sample_retrieval_eval.json
│       ├── offline_rag_eval.jsonl
│       └── reports/
├── eval/                         # 轻量离线评估样例
│   └── datasets/
│       └── rag_eval.jsonl
├── scripts/                      # 运维与评估脚本
│   ├── ingest_documents.py
│   ├── rebuild_vector_indexes.py
│   ├── run_rag_evaluation.py
│   └── evaluate_rag.py
├── tests/                        # pytest 测试套件
│   ├── conftest.py
│   ├── test_auth_api.py
│   ├── test_chat_api.py
│   ├── test_chat_service.py
│   ├── test_collection_api.py
│   ├── test_collection_service.py
│   ├── test_conversation_api.py
│   ├── test_conversation_service.py
│   ├── test_document_api.py
│   ├── test_document_path_strategy.py
│   ├── test_health_api.py
│   ├── test_milvus_integration.py
│   ├── test_rag_evaluation_api.py
│   ├── test_rag_evaluation_report_service.py
│   ├── test_rag_evaluation_service.py
│   ├── test_retrieval_service.py
│   ├── test_vector_store_service.py
│   └── test_web_page.py
├── test_data/                    # 测试夹具
├── venv/                         # Python 虚拟环境（gitignored）
├── .claude/                      # Claude Code 配置与 skills
│   └── skills/
│       └── paper_formatter.md
├── .env                          # 当前环境变量（gitignored）
├── .env.example                  # 环境变量模板
├── .gitignore
├── alembic.ini                   # Alembic 配置
├── ChatRobot_v3.0.py             # 旧 CLI 入口（兼容存根）
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── README.md
├── AGENTS.md                     # 本文件
├── PROJECT_HANDOFF_SUMMARY.md    # 项目交接文档
└── ENTERPRISE_RAG_REFACTOR_PLAN.md  # 原始重构计划
```

### 关键文件说明

- `app/main.py`：FastAPI 应用工厂、生命周期、中间件、metrics endpoint、静态文件挂载、路由注册。
- `app/core/config.py`：所有环境变量配置，统一通过 `Settings` 读取。
- `app/api/deps.py`：依赖构造与 service 单例，路由层应优先使用这里的依赖。
- `app/services/chat_service.py`：普通聊天与 SSE 流式聊天流程。
- `app/services/retrieval_service.py`：dense、hybrid、rerank 检索逻辑。
- `app/services/rag_evaluation_service.py`：完整 RAG 评估指标计算。
- `app/services/rag_evaluation_report_service.py`：评估数据集/报告的列表、加载与持久化。
- `scripts/run_rag_evaluation.py`：结构化 JSON 数据集评估入口。
- `scripts/evaluate_rag.py`：轻量 JSONL / 离线评估入口。
- `docker-compose.yml`：API、worker、PostgreSQL、Redis、可选 Milvus 组合服务。

---

## 4. 常用命令

### 环境准备

```powershell
# 安装依赖
pip install -r requirements.txt

# 复制环境变量模板并编辑
Copy-Item .env.example .env
# 然后编辑 .env，填入 OPENAI_API_KEY、JWT_SECRET_KEY 等真实值
```

### 本地基础设施

```powershell
# 启动 PostgreSQL + Redis
docker compose up -d postgres redis

# 可选：启动 Milvus 全套依赖（etcd + minio + milvus）
docker compose --profile milvus up -d etcd minio milvus
```

### 数据库迁移

```powershell
# 执行最新迁移
alembic upgrade head

# 查看当前版本
alembic current

# 查看迁移历史
alembic history

# 模型变更后生成新迁移
alembic revision --autogenerate -m "describe change"
```

### 运行应用

```powershell
# 本地开发启动 FastAPI
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Windows 本地启动 Celery Worker（建议使用 solo pool）
celery -A app.workers.celery_app.celery_app worker --loglevel=INFO --pool=solo
```

### Docker 整站部署

```powershell
docker compose up --build
```

访问地址：

- 本地开发页面：`http://127.0.0.1:8000/`
- Docker 整站页面：`http://127.0.0.1:8080/`
- Swagger UI：`http://127.0.0.1:8000/docs`
- 评估看板：`http://127.0.0.1:8000/evaluations`
- Prometheus metrics：`http://127.0.0.1:8000/metrics`

### 测试

```powershell
# 全量测试
python -m pytest

# 聚焦测试（来自 README 的推荐组合）
python -m pytest tests\test_auth_api.py tests\test_health_api.py tests\test_web_page.py tests\test_vector_store_service.py tests\test_chat_api.py tests\test_document_api.py tests\test_collection_service.py

# RAG 评估相关测试
python -m pytest tests\test_rag_evaluation_service.py tests\test_rag_evaluation_report_service.py tests\test_rag_evaluation_api.py

# 可选 Milvus 集成测试
$env:TEST_MILVUS_ENABLED="1"
python -m pytest tests\test_milvus_integration.py
```

最近一次完整验证结果：**66 passed, 1 skipped**。

### 代码/语法检查

```powershell
# Python 编译检查
python -m compileall app scripts tests

# 前端 JS 语法检查
node --check app\frontend\static\app.js
node --check app\frontend\static\evaluations.js
```

### 运维脚本

```powershell
# 重建向量索引
python scripts\rebuild_vector_indexes.py --backend faiss
python scripts\rebuild_vector_indexes.py --backend milvus
python scripts\rebuild_vector_indexes.py --backend milvus --collection-id <collection_id>
python scripts\rebuild_vector_indexes.py --backend milvus --document-id <document_id>

# 结构化 JSON 评估
python scripts\run_rag_evaluation.py --dataset data\evals\sample_retrieval_eval.json
python scripts\run_rag_evaluation.py --dataset data\evals\sample_retrieval_eval.json --answer-mode dataset
python scripts\run_rag_evaluation.py --dataset data\evals\sample_retrieval_eval.json --answer-mode generate
python scripts\run_rag_evaluation.py --dataset data\evals\sample_retrieval_eval.json --answer-mode dataset --llm-judge-mode auto
python scripts\run_rag_evaluation.py --dataset data\evals\sample_retrieval_eval.json --output data\evals\reports\latest.json

# 轻量 JSONL / 离线评估
python scripts\evaluate_rag.py --dataset eval\datasets\rag_eval.jsonl --collection-id <collection_id> --top-k 5
python scripts\evaluate_rag.py --dataset data\evals\offline_rag_eval.jsonl --answer-mode generate --output data\evals\reports\offline_latest.json
```

---

## 5. 代码规范和注意事项

### 架构分层

- **API Router**（`app/api/v1/`）：只处理 HTTP 层逻辑，调用 service 层。
- **Service**（`app/services/`）：放置业务逻辑，保持方法小而聚焦。
- **Repository**（`app/repositories/`）：放置数据库访问逻辑。
- **Schema**（`app/schemas/`）：放置 Pydantic 请求/响应/评估契约。
- **Vector Store**（`app/vectorstores/` + `app/services/vector_store_service.py`）：隔离 FAISS / Milvus 实现细节。

### 依赖注入

- 在 router 中优先使用 `app/api/deps.py` 里的依赖工厂，不要手动到处 new service。
- 单例通过 `@lru_cache` 管理。

### 用户隔离

- 必须保持用户隔离：`collections`、`documents`、`conversations`、`messages` 都是 owner-scoped。
- API 路由中通过 `current_user` 依赖获取当前用户，service/repository 层不要依赖全局用户。

### 文档入库流程

- 上传成功不代表文档已经入库。入库是异步流程：
  ```text
  uploaded -> queued -> processing -> indexed
  ```
- 失败路径：`uploaded/queued/processing -> failed`。
- 文档状态包括：`uploaded`、`queued`、`processing`、`indexed`、`failed`、`deleted`。

### 数据库变更

- 数据库结构变更优先使用 Alembic migration。
- `DB_AUTO_INIT=true` 适合本地开发，生产环境应设置 `DB_AUTO_INIT=false`，并显式执行 `alembic upgrade head`。
- 当前 bootstrap 迁移只实现了 `upgrade`，没有实现 `downgrade`。

### 环境变量与密钥

- 不要把 `.env` 里的密钥写入文档或示例；安全模板是 `.env.example`。
- 新增配置优先放入 `app/core/config.py` 的 `Settings` 类，并在 `.env.example` 中补充示例。

### RAG 配置与接口

- RAG 默认配置在 `app/core/config.py`：`rag_top_k`、hybrid search、rerank、query rewrite、context length、评估 judge model 等。
- `POST /api/v1/chat/completions` 支持请求级覆盖：`top_k`、`use_hybrid_search`、`use_rerank`、`use_query_rewrite`、`stream`。
- 流式聊天 SSE 事件顺序：`start`、多个 `token`、`sources`、`done`；失败时可能返回 `error`。

### 前端

- 前端是 `app/frontend` 下的原生 HTML/CSS/JavaScript，没有 bundler 或 npm install 步骤。
- 修改前端 JS 后，运行 `node --check` 检查语法。
- 前端页面路由由 `app/web/router.py` 提供。

### 代码风格

- 当前项目没有 `black`、`ruff`、`pyproject.toml` 等格式化 / lint 配置。
- 沿用本地风格：
  - 模块顶部使用 `from __future__ import annotations`。
  - 使用类型标注（Python 3.11 union syntax，如 `str | None`）。
  - 使用 Pydantic v2 models 定义请求/响应/评估 schema。
  - SQLAlchemy 2.0  declarative style：`Mapped` / `mapped_column`。
  - 手动语法验证：`python -m compileall` 和 `node --check`。

### 测试

- 现有测试大量使用 fake service / repository。
- 新增逻辑时优先补 service 单测和带 dependency override 的 API 测试。

### 依赖版本

- `requirements.txt` 未锁版本，不要把当前本地包版本当作 lockfile。
- 如需生产稳定，建议生成 `requirements.lock.txt` 或使用 pip-tools / uv lock。

### 向量后端

- FAISS 是更轻的本地后端，适合单机开发与 MVP。
- Milvus 需要 docker compose 的 `milvus` profile，并依赖 `etcd` 和 `minio`。
- 通过环境变量 `VECTOR_BACKEND=faiss|milvus` 切换。

### RAG 评估

- 评估报告默认存储在 `data/evals/reports/`。
- RAG 评估有两条路径：
  - `scripts/run_rag_evaluation.py` 和 API/看板使用 `data/evals` 下的结构化 JSON 数据集。
  - `scripts/evaluate_rag.py` 支持轻量 JSONL 评估，也可以输出 JSON 报告。

### 可观测性

- 可观测性由 `OBSERVABILITY_*` 配置控制。
- metrics 默认开启，访问 `/metrics`。
- tracing 需要显式开启并提供 OTLP endpoint。
- 所有 HTTP 响应都会回写 `X-Request-ID`，可用于前后端、Celery 和日志关联。

### 平台注意事项

- Windows 下 Celery 建议使用 `--pool=solo`。
- 如果 README 在 PowerShell 里显示乱码，优先认为源文件是 UTF-8，问题可能来自控制台编码。

### 已知限制 / 后续方向

- 当前 JWT 只有 access token，尚未实现 refresh token 流程。
- 上传成功只表示任务已进入队列，不代表向量入库已经完成。
- 稳定使用聊天能力需要 PostgreSQL、Redis、Celery Worker 同时运行。

---

*本文件由 AI Agent 扫描项目后生成，后续项目演进时请同步更新。*
