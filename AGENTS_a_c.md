# ChatRobot Enterprise RAG — AI 协作上下文文档

> 面向 AI 编码助手的项目全貌文档，用于快速建立上下文。最后更新：2026-08-12。

---

## 1. 项目简介

**ChatRobot_v3** 是一个企业级检索增强生成（RAG）知识问答系统。用户可以上传 PDF / DOCX / DOC / TXT 文档，系统通过 Celery 异步加载、递归切分、向量化并写入 FAISS 或 Milvus；对话时结合向量召回、关键词召回、RRF 融合、启发式重排和查询改写生成答案。项目还包含 RAG 评估体系，可后台运行评估、轮询进度并持久化报告。

当前核心能力：

- JWT 注册、登录、`/auth/me`，Swagger OAuth2 登录兼容
- collections / documents / conversations / messages 按用户隔离
- 文档上传、状态轮询、删除、重试入库和分块预览
- Celery + Redis 异步文档入库和 RAG 评估任务
- FAISS / Milvus 双向量后端，Milvus 通过 Compose profile 启动
- 递归切分器显式支持中英文句界、分句标点、逗号、空格和字符兜底
- Hybrid Search、RRF、Reranking、Query Rewriting
- `POST /api/v1/chat/completions` 支持 JSON 和 SSE 流式输出
- RAG 评估数据集、报告、后台进度查询和评估看板
- 生产化原生前端工作台：登录、注册、视图切换式工作台、文档任务、聊天、评估页面
- 首页工作台支持 overview / knowledge / documents / chat 真实视图切换，URL hash 可深链
- 前端统一提取 FastAPI 422 `detail[]`、后端 `message` 和纯文本错误，避免只显示泛化“请求失败”
- `proces.md` 记录待实施的 RAG 评测改进与 LangSmith 可选接入流程
- 结构化日志、Prometheus `/metrics`、可选 OpenTelemetry tracing

---

## 2. 技术栈

| 类别 | 技术 | 备注 |
|---|---|---|
| 语言 | Python 3.11 | Dockerfile 使用 `python:3.11-slim` |
| Web | FastAPI + Uvicorn | API、静态前端和 Swagger |
| 数据模型 | Pydantic v2 + pydantic-settings | `.env` 自动加载 |
| 数据库 | PostgreSQL 16 + SQLAlchemy | Alembic 管理 schema |
| 异步任务 | Celery + Redis 7 | 文档入库、RAG 评估进度 |
| 向量检索 | FAISS / Milvus 2.5 | `VECTOR_BACKEND` 切换 |
| RAG 编排 | LangChain + OpenAI API | 默认 `gpt-4o-mini` / `text-embedding-3-small` |
| 文档解析 | pypdf, docx2txt | PDF / Word / TXT |
| 前端 | 原生 HTML / CSS / JavaScript | FastAPI `StaticFiles` 托管 |
| 测试 | Pytest + FastAPI TestClient + httpx | Milvus 集成测试默认跳过 |
| 可观测性 | prometheus-client, opentelemetry-* | 指标默认可用，tracing 默认关闭 |

---

## 3. 目录结构

```text
ChatRobot_v3/
├── app/
│   ├── main.py                   # FastAPI 入口、lifespan、中间件、路由挂载
│   ├── api/
│   │   ├── deps.py               # DB、当前用户、service/repository 依赖
│   │   └── v1/
│   │       ├── auth.py           # 注册、登录、当前用户
│   │       ├── chat.py           # RAG 对话，含 SSE
│   │       ├── collections.py    # 知识库 CRUD 与入库触发
│   │       ├── documents.py      # 上传、查询、详情、删除、重试
│   │       ├── conversations.py  # 会话与消息
│   │       ├── health.py         # 健康检查
│   │       └── rag_evaluations.py # 数据集、报告、异步运行和进度查询
│   ├── core/                     # config、安全、日志、指标、tracing、路径安全
│   ├── db/models/                # user、collection、document、conversation、message
│   ├── schemas/                  # auth、chat、collection、document、rag_eval
│   ├── repositories/             # Repository 模式数据访问
│   ├── services/                 # 业务流程、检索、评估、任务队列
│   ├── rag/                      # loaders、splitters、retrieval、prompts
│   ├── vectorstores/             # base、faiss_store、milvus_store
│   ├── workers/                  # celery_app、ingest_document_task、run_rag_evaluation_task
│   ├── web/router.py             # `/`、`/register`、`/evaluations`
│   └── frontend/                 # 生产化工作台 HTML/CSS/JS
├── alembic/versions/             # 数据库迁移
├── scripts/                      # ingest、rebuild_vector_indexes、evaluate、run_rag_evaluation
├── tests/                        # API、service、RAG、worker、页面契约测试
├── docs/                         # 前端变更、修复和导航视图切换说明
├── data/evals/                   # 评估数据集、DeepSeek 数据集和 reports
├── data/raw|processed|faiss_indexes/
├── proces.md                     # RAG 评测改进与 LangSmith 接入实施流程（待实施）
├── docker-compose.yml            # api、worker、postgres、redis、milvus profile
├── Dockerfile
├── requirements.txt
├── .env.example
├── AGENTS.md                     # 短版仓库协作规则
└── AGENTS_a_c.md                 # 本文件，长版 AI 架构上下文
```

`tmp/`、`work/`、规划文件和 PDF 渲染产物属于本地协作/检查过程，不是主要业务源码。`proces.md` 是实施计划文档，不表示相关 schema、指标、LangSmith adapter 或 tracing 代码已经落地。

---

## 4. 常用命令

### 环境准备

```powershell
pip install -r requirements.txt
Copy-Item .env.example .env
```

编辑 `.env`，至少替换 `OPENAI_API_KEY` 和 `JWT_SECRET_KEY`。本地默认建议使用 `VECTOR_BACKEND=faiss`。

### 本地开发

```powershell
docker compose up -d postgres redis
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

另开终端：

```powershell
celery -A app.workers.celery_app.celery_app worker --loglevel=INFO --pool=solo
```

访问：

- 前端工作台：`http://127.0.0.1:8000/`
- 注册页：`http://127.0.0.1:8000/register`
- 评估看板：`http://127.0.0.1:8000/evaluations`
- Swagger：`http://127.0.0.1:8000/docs`
- 指标：`http://127.0.0.1:8000/metrics`

### Milvus / Docker

```powershell
docker compose --profile milvus up -d postgres redis etcd minio milvus
docker compose --profile milvus build
docker compose --profile milvus run --rm api alembic upgrade head
docker compose --profile milvus up -d api worker
```

使用 `VECTOR_BACKEND=milvus` 时，Compose 启停命令必须带 `--profile milvus`，否则 etcd、MinIO、Milvus 不会启动。

### 测试

```powershell
python -m pytest
python -m pytest tests/test_splitters.py -q
python -m pytest tests/test_task_queue_service.py tests/test_rag_evaluation_api.py -q
python -m pytest tests/test_web_page.py -q
```

Milvus 集成测试：

```powershell
$env:TEST_MILVUS_ENABLED="1"
python -m pytest tests/test_milvus_integration.py
```

---

## 5. 分层架构与修改边界

```text
api/v1 路由
  -> services 业务编排
    -> repositories 数据访问
    -> rag / vectorstores 检索与向量能力
    -> workers / task_queue 异步任务
```

修改时遵守：

- 路由层保持轻量，只处理 HTTP、认证依赖和响应模型
- 业务规则放入 `services/`
- SQLAlchemy 查询封装在 `repositories/`
- 依赖注入集中在 `app/api/deps.py`
- 数据库结构变更必须新增 Alembic migration
- 文件路径处理使用 `app/core/path_utils.py`
- 不顺手重构无关模块，不改变既有 API 行为和数据格式

---

## 6. RAG 与文档入库

入库流程：

```text
upload -> data/raw/ -> document metadata -> ingest_document_task
-> loaders -> split_documents -> embedding -> FAISS/Milvus -> document status
```

状态流转：

```text
uploaded -> queued -> processing -> indexed
uploaded/queued/processing -> failed
deleted
```

递归切分配置在 `app/rag/splitters.py`：

- 分隔符优先级：段落、换行、中文句末标点、英文句末标点、分句标点、逗号、空格、空字符串
- `keep_separator="end"`，句末标点保留在前一个分块
- `chunk_id` 仍为 `{document_id}-{index}`，同一输入和配置下确定
- 修改切分规则后，旧索引不会自动更新，必须重建实际后端索引

重建命令：

```powershell
python scripts/rebuild_vector_indexes.py --backend faiss --document-id <document_id>
python scripts/rebuild_vector_indexes.py --backend milvus --collection-id <collection_id>
```

重建会先删除目标文档旧向量，优先在可恢复的测试文档上试跑。

---

## 7. RAG 评估体系

数据集位于 `data/evals/`，报告位于 `data/evals/reports/`。当前包含示例数据集和 `deepseek_academic_prompts_eval.json`，后者基于 38 页 DeepSeek 学术提示词 PDF，包含 31 个带来源文件和证据页的评估案例。

主要 schema 在 `app/schemas/rag_eval.py`：

- `RagEvaluationDataset`
- `RagEvaluationCase`
- `RagEvaluationRunRequest`
- `RagEvaluationStoredReport`
- `RagEvaluationTaskStatus`

后端接口：

- `GET /api/v1/evaluations/rag/datasets`
- `GET /api/v1/evaluations/rag/reports`
- `GET /api/v1/evaluations/rag/reports/{report_id}`
- `POST /api/v1/evaluations/rag/run`：返回 `202 Accepted`、`task_id`、`total_cases`
- `GET /api/v1/evaluations/rag/runs/{task_id}`：返回 queued/running/completed/failed、完成数、总数、报告或错误

评估由 `run_rag_evaluation_task` 后台执行，并通过 Celery result backend 保存进度。保持 `CELERY_TASK_IGNORE_RESULT=false`，否则页面无法查询进度。报告列表按 `created_at` 解析后的时间倒序排列。

---

## 8. 前端上下文

前端入口：

- `app/frontend/index.html`
- `app/frontend/register.html`
- `app/frontend/evaluations.html`
- `app/frontend/static/app.css`
- `app/frontend/static/app.js`
- `app/frontend/static/register.js`
- `app/frontend/static/evaluations.js`

当前 UI 是生产化工作台结构，静态资源版本为 `20260811.5`。首页认证后使用产品顶栏、工作台侧栏和单视图工作区；侧栏不再滚动到同页区域，而是通过按钮驱动真正的视图切换。

首页视图：

- `overview`：入口卡片、快捷操作、最近活动和概览统计
- `knowledge`：知识库选择、创建和上传队列
- `documents`：独立文档任务视图、`documentsCollectionSelect`、文档列表和详情
- `chat`：当前知识库下的对话、来源和流式回答

`app/frontend/static/app.js` 维护 `state.activeView`，通过 `setActiveView()` 同步 `.is-active`、`aria-pressed` 和 URL hash。旧 hash 如 `#knowledgePanel` 仍应兼容到新视图。文档任务导航有 `navDocumentsBadge`，显示待处理文档数量。`workspaceRefreshButton` 和 `refreshDocumentsViewButton` 分别支持概览/文档视图刷新。

错误处理统一使用 `extractErrorMessage()`，覆盖后端 `{message}`、FastAPI 422 `{detail: [{msg}]}` 和纯文本响应。新增或修改请求失败路径时不要回退到只读 `payload.message`。

修改前端时必须保留现有 DOM id 和业务脚本钩子，例如 `collectionSelect`、`documentsCollectionSelect`、`workspaceStats`、`workspaceActions`、`recentActivityList`、`evalCollectionSelect`、`evalRunProgressBar`。页面测试 `tests/test_web_page.py` 会锁定产品顶栏、侧栏、view switching、文档视图独立知识库选择、概览动作区、label、aria-live、评估进度和 collection 选择契约。

相关说明文档：

- `docs/CHANGES-2026-08-11.md`
- `docs/frontend-fixes-2026-08-11.md`
- `docs/nav-view-switching-2026-08-11.md`

---

## 9. 关键配置

常见配置位于 `.env.example` 和 `app/core/config.py`：

| 变量 | 用途 |
|---|---|
| `OPENAI_API_KEY` | OpenAI API 密钥 |
| `OPENAI_MODEL` / `OPENAI_EMBEDDING_MODEL` | 对话与 embedding 模型 |
| `VECTOR_BACKEND` | `faiss` 或 `milvus` |
| `RAG_CHUNK_SIZE` / `RAG_CHUNK_OVERLAP` | 按 Python 字符数计算的切分参数 |
| `RAG_USE_HYBRID_SEARCH` / `RAG_USE_RERANK` | 检索增强开关 |
| `RAG_QUERY_REWRITE_ENABLED` | 多轮追问改写开关 |
| `DATABASE_URL` / `POSTGRES_*` | 数据库连接 |
| `REDIS_URL` / `CELERY_*` | Celery broker/result backend |
| `CELERY_TASK_IGNORE_RESULT` | 必须为 `false` 才能查询评估进度 |
| `DB_AUTO_INIT` | 生产建议为 `false` |
| `UPLOAD_MAX_BYTES` / `ALLOWED_UPLOAD_EXTENSIONS` | 上传限制 |

---

## 10. RAG 评测改进规划

`proces.md` 定义了后续评测体系升级流程，状态为“待实施”。它基于当前递归切分、混合检索、重排、31 题 DeepSeek 数据集、异步评估和前端看板，规划以下方向：

- source-only 数据集不要生成误导性的 chunk/document 主指标
- 引入稳定 `document_key`、`relevant_evidence`、证据页码、quote hash 和 relevance grade
- 用 `required_facts` / `forbidden_claims` / `answerable` 评价回答完整性、正确性和拒答
- 区分“标准证据回答路径”和“实际召回答案路径”，定位检索问题还是生成问题
- Judge 应使用独立模型，避免静默回退到回答模型自评
- 将用户问答延迟、离线评估耗时和 Judge 耗时拆开统计，并补充 query rewrite、embedding、dense/keyword、fusion、rerank、context build、TTFT 等阶段
- LangSmith 仅作为可选 tracing、实验比较、人工 annotation queue 和线上抽样层，不替代本地评估报告

下一次代码实施建议只处理 `proces.md` 的“阶段 1：修正 source-only 指标语义”，不要同时引入 evidence schema、LangSmith 或延迟优化。

---

## 11. 测试地图

重点测试文件：

- `tests/test_auth_api.py`
- `tests/test_collection_api.py` / `tests/test_collection_service.py`
- `tests/test_document_api.py` / `tests/test_document_path_strategy.py`
- `tests/test_chat_api.py` / `tests/test_chat_service.py`
- `tests/test_retrieval_service.py`
- `tests/test_splitters.py`
- `tests/test_rag_evaluation_service.py`
- `tests/test_rag_evaluation_report_service.py`
- `tests/test_rag_evaluation_api.py`
- `tests/test_task_queue_service.py`
- `tests/test_web_page.py`
- `tests/test_milvus_integration.py`

新增或修改行为时优先写失败测试，再做最小实现。外部服务通过 fake、依赖覆盖或 monkeypatch 隔离；Milvus 测试需显式启用。

最近一次本文档刷新后的验证结果：

```text
C:\ProgramData\anaconda3\python.exe -m pytest tests/test_web_page.py tests/test_splitters.py tests/test_task_queue_service.py tests/test_rag_evaluation_api.py tests/test_rag_evaluation_report_service.py -q
# 25 passed, 1 warning

C:\ProgramData\anaconda3\python.exe -m pytest -q
# 85 passed, 1 skipped, 1 warning
```

warning 通常为既有 Starlette `python_multipart` 导入弃用提醒；skip 通常为默认关闭的 Milvus 集成测试。

---

## 12. 安全与协作规则

- 不提交 `.env`、API key、JWT secret、真实文档、生成索引、本地报告或 PDF 渲染临时产物
- 新配置同步更新 `.env.example` 和相关文档
- 生产环境使用 Alembic 管理 schema，不依赖自动建表
- 修改 API、schema、任务状态或前端 DOM 契约时同步更新测试
- 如果涉及索引重建、Docker profile、Celery 结果后端或 Milvus 连接，必须在反馈中明确影响范围和验证命令
