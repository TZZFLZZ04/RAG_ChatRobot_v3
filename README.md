# ChatRobot_v3

`ChatRobot_v3` 是一个面向企业知识问答场景的 RAG 应用，基于 FastAPI、PostgreSQL、SQLAlchemy、Celery、Redis，以及可切换的 FAISS / Milvus 向量后端构建。

当前已完成的核心能力：

- JWT 用户系统，支持注册、登录、`GET /api/v1/auth/me`
- 兼容 Swagger OAuth2 的登录流程
- collections / documents / conversations / messages 按用户隔离
- Celery + Redis 异步文档入库
- FAISS / Milvus 双向量后端切换
- `POST /api/v1/chat/completions` 支持普通 JSON 与 `stream=true` 的 SSE 流式输出
- 前端已支持登录、知识库管理、上传队列、文档状态、文档详情与分块预览、删除、重试入库和聊天

## 项目结构

```text
app/
  api/                FastAPI 路由
  core/               配置、安全、异常
  db/                 SQLAlchemy Base、Session、ORM 模型
  frontend/           HTML / CSS / JavaScript 前端
  rag/                loader、splitter、prompt
  repositories/       PostgreSQL 仓储层
  schemas/            Pydantic 模型
  services/           业务服务层
  vectorstores/       FAISS / Milvus 实现
  web/                Web 页面路由
  workers/            Celery app 与任务
alembic/              数据库迁移
data/                 原始文件、处理中间文件、FAISS 索引
scripts/              辅助脚本
tests/                测试
```

## 安装依赖

```powershell
pip install -r requirements.txt
```

## 环境变量

先复制环境变量模板：

```powershell
Copy-Item .env.example .env
```

重点变量如下：

```env
OBSERVABILITY_LOG_JSON=true
OBSERVABILITY_METRICS_ENABLED=true
OBSERVABILITY_TRACING_ENABLED=false
OBSERVABILITY_SERVICE_NAME=chatrobot-api
OBSERVABILITY_OTLP_ENDPOINT=http://localhost:4318/v1/traces

OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
RAG_EVAL_LLM_JUDGE_MODEL=

JWT_SECRET_KEY=replace-this-secret-key
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRES_MINUTES=1440

DATABASE_URL=
DB_AUTO_INIT=true
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=chatrobot
POSTGRES_PASSWORD=chatrobot
POSTGRES_DB=chatrobot

REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=
CELERY_RESULT_BACKEND=

RAG_CHUNK_SIZE=500
RAG_CHUNK_OVERLAP=80

VECTOR_BACKEND=faiss
MILVUS_URI=
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_COLLECTION=chatrobot_documents
```

说明：

- `DATABASE_URL` 优先级高于 `POSTGRES_*`
- `CELERY_BROKER_URL` 和 `CELERY_RESULT_BACKEND` 未设置时会回退到 `REDIS_URL`
- `RAG_CHUNK_SIZE` 和 `RAG_CHUNK_OVERLAP` 按 Python 字符数计算，不是模型 token 数；须保持 `0 <= RAG_CHUNK_OVERLAP < RAG_CHUNK_SIZE`
- `MILVUS_URI` 优先级高于 `MILVUS_HOST` / `MILVUS_PORT`
- `DB_AUTO_INIT=true` 时，应用启动仍会保留本地开发用的自动建表行为
- 生产环境建议设置 `DB_AUTO_INIT=false`，只通过 Alembic 管理数据库结构
- `OBSERVABILITY_METRICS_ENABLED=true` 时，应用会暴露 `GET /metrics` Prometheus 指标
- `OBSERVABILITY_TRACING_ENABLED=true` 时，需要同时安装 OpenTelemetry instrumentation 依赖并提供 OTLP endpoint

## Alembic 数据库迁移

项目现已接入 Alembic，用于统一管理数据库 schema。

执行最新迁移：

```powershell
alembic upgrade head
```

模型变更后生成新迁移：

```powershell
alembic revision --autogenerate -m "描述本次变更"
```

查看当前数据库版本：

```powershell
alembic current
```

查看迁移历史：

```powershell
alembic history
```

### 生产环境建议

建议按以下顺序部署：

1. 设置 `DB_AUTO_INIT=false`
2. 执行 `alembic upgrade head`
3. 启动 FastAPI
4. 启动 Celery Worker

### 现有数据库升级说明

首个迁移 `20260428_01` 同时支持：

- 全新空的 PostgreSQL 数据库初始化
- 旧版本数据库升级到当前 schema

它会补齐旧库缺失的 `owner_id` 字段，并把 collection 名称约束从旧的“全局唯一”升级为：

```text
(owner_id, name) 唯一
```

注意：

- 旧数据里的 collection / document / conversation 不会自动归属到新用户，缺失的 `owner_id` 仍需要你手工回填或重新导入
- 当前 bootstrap 迁移只实现了 `upgrade`，没有实现 `downgrade`

## 运行模式

| 模式 | API / Worker | PostgreSQL / Redis | 向量后端 | 访问地址 |
|------|--------------|--------------------|----------|----------|
| 本地开发 | 宿主机运行 | Docker | 默认 FAISS，可选 Milvus | `http://127.0.0.1:8000/` |
| 全 Docker 部署 | Docker | Docker | Milvus | `http://127.0.0.1:8080/` |

## 本地开发

本地开发默认使用 FAISS。确认 `.env` 包含：

```env
VECTOR_BACKEND=faiss
MILVUS_HOST=localhost
```

启动 PostgreSQL、Redis，执行迁移，然后分别启动 API 和 Worker：

```powershell
docker compose up -d postgres redis
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

另开一个终端启动 Worker：

```powershell
celery -A app.workers.celery_app.celery_app worker --loglevel=INFO --pool=solo
```

如需在本地开发时使用 Milvus，将 `VECTOR_BACKEND` 改为 `milvus`，保持 `MILVUS_HOST=localhost`，并启动完整依赖：

```powershell
docker compose --profile milvus up -d postgres redis etcd minio milvus
```

## 全 Docker 部署（Milvus）

全 Docker 模式会运行 API、Worker、PostgreSQL、Redis、etcd、MinIO 和 Milvus。首次部署前复制并编辑 `.env`：

```powershell
Copy-Item .env.example .env
```

至少确认以下配置，并替换真实密钥：

```env
APP_ENV=prod
APP_DEBUG=false
DB_AUTO_INIT=false
VECTOR_BACKEND=milvus
DATABASE_URL=
MILVUS_URI=
OPENAI_API_KEY=your_api_key_here
JWT_SECRET_KEY=replace-with-a-strong-secret
```

`DATABASE_URL` 和 `MILVUS_URI` 留空时，Compose 会自动将容器内连接地址设置为 `postgres`、`redis` 和 `milvus`。不要在这两个变量中填写指向 `localhost` 的容器连接地址。

首次部署或升级时，按顺序执行：

```powershell
docker compose --profile milvus build
docker compose --profile milvus up -d postgres redis etcd minio milvus
docker compose --profile milvus run --rm api alembic upgrade head
docker compose --profile milvus up -d api worker
```

检查服务状态和关键日志：

```powershell
docker compose --profile milvus ps
docker compose --profile milvus logs --tail=100 api worker milvus
Invoke-RestMethod http://127.0.0.1:8080/api/v1/health
Test-NetConnection 127.0.0.1 -Port 19530
```

日常启动、跟踪日志和停止：

```powershell
docker compose --profile milvus up -d
docker compose --profile milvus logs -f api worker milvus
docker compose --profile milvus down
```

`down` 会停止并删除容器和网络，但保留命名卷中的 PostgreSQL、MinIO、etcd 与 Milvus 数据。使用 `VECTOR_BACKEND=milvus` 时，所有 Compose 启停命令都必须带 `--profile milvus`，否则 Milvus 依赖栈不会启动。

## 核心 API

公开接口：

- `GET /`
- `GET /api/v1/health`
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`

受保护接口：

- `GET /api/v1/auth/me`
- `GET /api/v1/collections`
- `POST /api/v1/collections`
- `POST /api/v1/collections/{collection_id}/ingest`
- `POST /api/v1/documents/upload`
- `GET /api/v1/documents`
- `GET /api/v1/documents/{document_id}`
- `POST /api/v1/documents/{document_id}/retry`
- `DELETE /api/v1/documents/{document_id}`
- `POST /api/v1/chat/completions`

## 文档入库流程

1. 用户上传一个或多个文件
2. API 将原始文件保存到 `data/raw/`
3. API 在 PostgreSQL 中写入 document 元数据
4. API 投递 `ingest_document_task`
5. Celery Worker 执行加载、切分、embedding、写入向量库
6. 文档状态按以下流程推进：

```text
uploaded -> queued -> processing -> indexed
```

失败路径：

```text
uploaded/queued/processing -> failed
```

当前文档状态包括：

- `uploaded`
- `queued`
- `processing`
- `indexed`
- `failed`
- `deleted`

## 前端能力

首页 `GET /` 当前已支持：

- 登录页与独立注册页
- JWT 本地持久化与登录恢复
- 当前用户信息展示
- 知识库切换与创建
- 多文件上传队列反馈
- 文档状态自动轮询
- 单文档删除
- 单文档重试入库
- 文档详情与分块预览
- 会话历史列表与会话详情回放
- 会话历史独立滚动窗口
- 中断当前回答
- token 级流式聊天渲染
- 回答结束后的来源延迟回填

当前首页已统一为 `ChatRobot_v3 RAG 工作台`，采用“左侧知识库与文档中心 + 右侧知识问答”的双栏布局。左右主框架当前使用统一的较长高度；右侧回答正文区域占比更大，消息区固定在卡片内上下滚动；左侧会话历史也已支持独立滚动，避免会话过多时挤压布局。

## 向量后端切换

### FAISS

适合：

- 单机开发
- MVP
- 简单本地部署

```env
VECTOR_BACKEND=faiss
```

### Milvus

适合：

- 共享环境
- 更大规模文档量
- 更生产化的向量检索

```env
VECTOR_BACKEND=milvus
```

当前 Milvus chunk schema 包含：

- `id`
- `collection_id`
- `document_id`
- `chunk_id`
- `chunk_index`
- `text`
- `source_name`
- `source_path`
- `metadata_json`
- `embedding`
- `created_at`

## 重建向量索引

常用命令：

```powershell
python scripts/rebuild_vector_indexes.py --backend milvus
python scripts/rebuild_vector_indexes.py --backend milvus --collection-id <collection_id>
python scripts/rebuild_vector_indexes.py --backend milvus --document-id <document_id>
python scripts/rebuild_vector_indexes.py --backend faiss
```

切分器会依次优先使用段落、换行、中英文句末标点、分句标点、逗号和空格，最后按字符兜底；句末标点保留在前一个分块。修改切分配置或切分规则后，已有向量不会自动更新，必须为实际使用的 FAISS / Milvus 后端重建索引。建议先用 `--document-id` 对可恢复的测试文档试跑，再扩大范围；重建会先删除目标文档的旧索引。

## RAG 检索增强

当前版本已补充三层检索增强能力：

- `Hybrid Search`：同时执行向量召回与关键词召回，并使用 `RRF (Reciprocal Rank Fusion)` 融合结果
- `Reranking`：对融合后的候选分块按词覆盖率、短语命中、标题命中等信号进行二次重排
- `Query Rewriting`：针对多轮追问自动改写检索查询，将上下文相关的追问改写为更适合检索的独立问题

推荐将以下配置项加入 `.env`：

```env
RAG_USE_HYBRID_SEARCH=true
RAG_USE_RERANK=true
RAG_HYBRID_CANDIDATE_MULTIPLIER=3
RAG_HYBRID_RRF_K=60
RAG_KEYWORD_SCORE_THRESHOLD=0.2
RAG_QUERY_REWRITE_ENABLED=true
RAG_QUERY_REWRITE_HISTORY_MESSAGES=6
RAG_QUERY_REWRITE_MAX_CHARS=300
```

`POST /api/v1/chat/completions` 现在支持以下可选参数，用于按请求覆盖默认行为：

- `use_hybrid_search`
- `use_rerank`
- `use_query_rewrite`

## RAG 评估体系

当前项目已补充一套覆盖“检索质量 + 回答质量 + groundedness”的 RAG 评估体系，特点如下：

- 使用独立 JSON 数据集描述评估 case，不依赖前端或 HTTP 接口
- 支持 `collection_id`、`top_k`、`use_hybrid_search`、`use_rerank` 的数据集级和 case 级覆盖
- 同时支持 `relevant_chunk_ids` 与 `relevant_document_ids` 两种标注粒度
- 自动输出 `Precision@K`、`Recall@K`、`HitRate@K`、`MRR@K`、`MAP@K`、`NDCG@K`
- 当同时提供 chunk 和 document 标注时，默认以 chunk 作为 primary metric，并保留 document 指标
- 支持 `candidate_answer` 直接评分，也支持基于当前 RAG 检索结果自动生成答案再评分
- 自动输出 `overall_answer_score`、`groundedness_score`、`grounded_sentence_ratio`、`query_term_coverage`
- 如果提供 `expected_answer_contains` 或 `reference_answer`，会额外计算答案覆盖率与参考答案相似度
- 支持可选 `LLM judge`，会和启发式答案分数并排输出，不替换已有指标

新增文件：

- `app/schemas/rag_eval.py`：评估数据集、case、检索/答案报告 schema
- `app/services/rag_evaluation_service.py`：检索评估、答案评估、groundedness 评分与指标聚合
- `scripts/run_rag_evaluation.py`：命令行评估入口
- `data/evals/sample_retrieval_eval.json`：示例评估集模板

数据集示例：

```json
{
  "dataset_name": "sample-retrieval-eval",
  "default_collection_id": "your-collection-id",
  "default_top_k": 5,
  "default_use_hybrid_search": true,
  "default_use_rerank": true,
  "cases": [
    {
      "case_id": "leave-policy-annual-leave",
      "query": "员工年假制度是什么？",
      "relevant_chunk_ids": ["chunk-id-1"],
      "relevant_document_ids": ["document-id-1"],
      "reference_answer": "员工年假制度包含年假规则和审批流程。",
      "candidate_answer": "员工年假制度包含年假规则与审批流程。",
      "expected_answer_contains": ["年假", "审批流程"]
    }
  ]
}
```

运行方式：

```powershell
python scripts/run_rag_evaluation.py --dataset data/evals/sample_retrieval_eval.json
python scripts/run_rag_evaluation.py --dataset data/evals/sample_retrieval_eval.json --answer-mode dataset
python scripts/run_rag_evaluation.py --dataset data/evals/sample_retrieval_eval.json --answer-mode generate
python scripts/run_rag_evaluation.py --dataset data/evals/sample_retrieval_eval.json --answer-mode dataset --llm-judge-mode auto
python scripts/run_rag_evaluation.py --dataset data/evals/sample_retrieval_eval.json --answer-mode generate --llm-judge-mode require
python scripts/run_rag_evaluation.py --dataset data/evals/sample_retrieval_eval.json --top-k 3
python scripts/run_rag_evaluation.py --dataset data/evals/sample_retrieval_eval.json --use-hybrid-search true --use-rerank true
python scripts/run_rag_evaluation.py --dataset data/evals/sample_retrieval_eval.json --output data/evals/reports/latest.json
```

输出说明：

- stdout 会打印完整 JSON 报告
- `summary.primary_metrics` 表示当前数据集的主指标均值
- `summary.chunk_metrics` / `summary.document_metrics` 会分别汇总不同标注粒度的结果
- `summary.answer_metrics` 会汇总答案质量和 groundedness 的均值
- `case_results[].answer_metrics` 会输出单条答案的 `overall_answer_score`、`groundedness_score`、`unsupported_statements`
- `--answer-mode dataset` 会直接评分数据集中的 `candidate_answer`
- `--answer-mode generate` 会基于当前检索结果自动生成答案后再评分，要求 `OPENAI_API_KEY` 可用
- `summary.llm_judge_metrics` 会汇总 LLM judge 的 `overall_score`、`groundedness_score`、`relevance_score`
- `case_results[].llm_judge_metrics` 会保留 LLM judge 的 strengths、weaknesses 和 rationale
- `--llm-judge-mode auto` 会在可用时执行 judge，不可用时跳过并写入 notes
- `--llm-judge-mode require` 会把 judge 视为强约束，失败时直接报错
- `RAG_EVAL_LLM_JUDGE_MODEL` 可单独指定 judge 使用的模型；为空时回退到 `OPENAI_MODEL`
- `case_results` 会保留每个 query 的召回结果、答案、主指标和备注，便于排查失败 case

## 测试

主测试命令：

```powershell
python -m pytest tests\test_auth_api.py tests\test_health_api.py tests\test_web_page.py tests\test_vector_store_service.py tests\test_chat_api.py tests\test_document_api.py tests\test_collection_service.py
```

可选的 Milvus 集成测试：

```powershell
$env:TEST_MILVUS_ENABLED="1"
python -m pytest tests\test_milvus_integration.py
```

最近一次完整验证结果：

```powershell
node --check app\frontend\static\evaluations.js
node --check app\frontend\static\app.js
python -m compileall app scripts tests
python -m pytest
```

结果为：

- `66 passed, 1 skipped`

## Observability

- 所有 HTTP 响应都会回写 `X-Request-ID`，可用于前后端、Celery 和日志关联
- API 访问、错误异常、Celery 任务都会输出结构化 JSON 日志
- `GET /metrics` 暴露 HTTP 请求、延迟、异常和 Celery 任务指标
- OpenTelemetry tracing 默认关闭，开启后会对 FastAPI、SQLAlchemy、Celery 进行 tracing instrumentation

## 运维注意事项

- 上传成功只表示任务已进入队列，不代表向量入库已经完成
- 稳定使用聊天能力需要 PostgreSQL、Redis、Celery Worker 同时运行
- 当前 JWT 仍然只有 access token，尚未实现 refresh token 流程
- Alembic 已接入仓库，但如果本地环境还没安装依赖，需要先重新执行 `pip install -r requirements.txt`
## 评估报告看板

为了方便持续观察 RAG 基线变化，当前版本已经新增评估报告后端 API 和前端管理页。

后端接口：
- `GET /api/v1/evaluations/rag/datasets`
- `GET /api/v1/evaluations/rag/reports`
- `GET /api/v1/evaluations/rag/reports/{report_id}`
- `POST /api/v1/evaluations/rag/run`：返回 `202 Accepted` 和后台任务 ID
- `GET /api/v1/evaluations/rag/runs/{task_id}`：查询完成数、总数、状态和最终报告

前端入口：
- `GET /evaluations`
- 首页已经增加“评估看板”入口

当前能力：
- 可直接读取 `data/evals/` 下的数据集
- 通过 Celery Worker 在后台运行评估，并按逐 case 进度显示“已完成 X/总数”
- 可把结果持久化到 `data/evals/reports/`，历史报告按 `created_at` 倒序展示
- 可查看历史报告摘要、完整 summary 和逐 case 结果
- 可在页面里切换 `answer_mode` 与 `llm_judge_mode`
- 可覆盖 `collection_id`、`top_k`、`use_hybrid_search`、`use_rerank`

API 调用示例：

```powershell
$run = Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/evaluations/rag/run `
  -Headers @{ Authorization = "Bearer <access_token>" } `
  -ContentType "application/json" `
  -Body '{
    "dataset_path": "sample_retrieval_eval.json",
    "answer_mode": "dataset",
    "llm_judge_mode": "auto",
    "persist": true
  }'

Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/v1/evaluations/rag/runs/$($run.task_id)" `
  -Headers @{ Authorization = "Bearer <access_token>" }
```

评估不再占用 API 请求线程，但必须保持 Redis 和 Celery Worker 运行。任务进度存储在 Celery 结果后端；如果设置 `CELERY_TASK_IGNORE_RESULT=true`，进度查询将不可用。
