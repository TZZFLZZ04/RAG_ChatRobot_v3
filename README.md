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

VECTOR_BACKEND=faiss
MILVUS_URI=
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_COLLECTION=chatrobot_documents
```

说明：

- `DATABASE_URL` 优先级高于 `POSTGRES_*`
- `CELERY_BROKER_URL` 和 `CELERY_RESULT_BACKEND` 未设置时会回退到 `REDIS_URL`
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

## 本地运行

### 1. 启动基础服务

```powershell
docker compose up -d postgres redis
```

如果需要 Milvus：

```powershell
docker compose --profile milvus up -d etcd minio milvus
```

### 2. 执行数据库迁移

推荐先执行：

```powershell
alembic upgrade head
```

### 3. 启动 FastAPI

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. 启动 Celery Worker

```powershell
celery -A app.workers.celery_app.celery_app worker --loglevel=INFO --pool=solo
```

### 5. 打开页面

```text
http://127.0.0.1:8000/
```

## Docker 整站模式

```powershell
docker compose up --build
```

访问地址：

```text
http://127.0.0.1:8080/
```

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
node --check app\frontend\static\app.js
python -m compileall app tests
python -m pytest
```

结果为：

- `51 passed, 1 skipped`

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
