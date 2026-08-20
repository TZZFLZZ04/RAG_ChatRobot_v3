# ChatRobot_v3 项目交接总结

## 1. 项目定位

`ChatRobot_v3` 已经从早期 Demo 演进为一个可持续开发的企业级 RAG 工作台，当前目标是：

- 提供可直接访问的 Web 工作台
- 支持用户注册、登录、JWT 鉴权和按用户隔离的数据权限
- 支持知识库、文档上传、异步入库、会话历史和聊天问答
- 支持 FAISS / Milvus 双向量后端切换
- 支持本地开发、Docker 部署、Alembic 迁移和 Celery 异步任务
- 支持基础可观测性与 RAG 评估闭环，便于持续优化检索和回答质量

当前系统已经不是单文件样例，而是完整的前后端一体化 FastAPI 项目。

## 2. 当前已完成能力

### 后端基础

- `FastAPI + PostgreSQL + SQLAlchemy`
- 统一 `.env` 配置管理
- `GET /` 首页
- `/api/v1/...` 版本化 API
- `Alembic` 已接入并用于数据库迁移

### 用户与认证

- 用户注册：`POST /api/v1/auth/register`
- 用户登录：`POST /api/v1/auth/login`
- 当前用户：`GET /api/v1/auth/me`
- JWT access token 鉴权
- Swagger OAuth2 登录兼容
- 登录兼容“用户名或邮箱”

### 权限隔离

以下资源已经绑定 `owner_id` 并按用户隔离：

- collections
- documents
- conversations
- messages

其中知识库名称约束已经从“全局唯一”调整为“同一用户内唯一”。

### 知识库与文档

- 知识库创建与查询
- 文档上传
- 文档元数据写入 PostgreSQL
- Celery + Redis 异步入库
- 文档列表与状态查询
- 单文档删除
- 单文档重试入库
- 文档详情与 chunk 预览
- 上传队列反馈与失败原因展示

当前文档状态包括：

- `uploaded`
- `queued`
- `processing`
- `indexed`
- `failed`
- `deleted`

### 向量检索

- `FAISS` 已支持
- `Milvus` 已支持
- 可通过 `VECTOR_BACKEND` 切换
- 已提供向量索引重建脚本

### RAG 检索增强

当前已完成三层检索增强：

- `Hybrid Search`：向量召回 + 关键词召回，并用 `RRF` 融合
- `Reranking`：基于词覆盖率、短语命中、标题命中做二次重排
- `Query Rewriting`：针对多轮追问自动改写检索查询

### 聊天问答

- 基于指定知识库进行 RAG 问答
- conversation 维持上下文
- 非流式问答
- 流式问答 `stream=true`
- SSE `text/event-stream`
- 会话历史列表
- 会话详情回放
- 前端支持“中断回答”
- 前端支持 token 级实时渲染
- 前端支持来源延迟回填

### 前端工作台

首页当前已具备：

- 登录页与独立注册页
- 登录态恢复
- token 失效提示
- 当前用户信息展示
- 知识库选择与创建
- 批量文档上传
- 上传队列反馈
- 文档状态自动轮询
- 文档详情与 chunk 预览
- 单文档删除 / 重试入库
- 会话历史列表
- 会话历史独立滚动窗口
- token 级流式回答
- 来源延迟回填
- 中断回答

当前主工作台已经统一为 `ChatRobot_v3 RAG 工作台`，采用左右等高主框架，右侧回答区更大，左右列表均支持独立滚动。

## 3. 本轮新增与改进内容

### 可观测性

当前版本已经补齐一套基础 observability 能力：

- 结构化 JSON 日志
- request id middleware
- API latency logging
- Celery task logging
- Prometheus `/metrics`
- OpenTelemetry tracing 接入点
- 错误审计日志

当前行为：

- 所有 HTTP 响应都会回写 `X-Request-ID`
- API / 异常 / Celery 任务都会输出结构化日志
- `/metrics` 暴露 HTTP 与 Celery 指标
- tracing 默认关闭，可通过环境变量开启

### RAG 评估体系

当前项目已经补齐一套覆盖“检索质量 + 回答质量 + groundedness”的 RAG 评估体系：

- 支持独立 JSON 数据集
- 支持 `collection_id`、`top_k`、`use_hybrid_search`、`use_rerank` 覆盖
- 支持 `relevant_chunk_ids` 和 `relevant_document_ids` 两种标注粒度
- 输出 `Precision@K`、`Recall@K`、`HitRate@K`、`MRR@K`、`MAP@K`、`NDCG@K`
- 支持 `candidate_answer` 直接评分
- 支持基于当前检索结果自动生成答案再评分
- 输出 `overall_answer_score`、`groundedness_score`、`grounded_sentence_ratio`
- 支持 `expected_answer_contains` 和 `reference_answer`

### LLM Judge

在启发式答案评分之外，当前还支持可选的 `LLM judge`，并与启发式分数并存输出，不相互替代。

支持模式：

- `off`
- `auto`
- `require`

当前会输出的 LLM judge 维度包括：

- `overall_score`
- `groundedness_score`
- `relevance_score`
- `completeness_score`
- `factual_consistency_score`
- `strengths`
- `weaknesses`
- `rationale`

### 评估报告 API 与管理页

为了方便持续观察基线变化，当前版本已经把评估报告挂到后端 API 和前端管理页：

后端接口：

- `GET /api/v1/evaluations/rag/datasets`
- `GET /api/v1/evaluations/rag/reports`
- `GET /api/v1/evaluations/rag/reports/{report_id}`
- `POST /api/v1/evaluations/rag/run`

前端入口：

- `GET /evaluations`
- 首页已经增加“评估看板”入口

当前看板能力：

- 选择评估数据集
- 覆盖 `collection_id`
- 覆盖 `top_k`
- 切换 `use_hybrid_search`
- 切换 `use_rerank`
- 切换 `answer_mode`
- 切换 `llm_judge_mode`
- 查看历史报告摘要
- 查看完整 summary
- 查看逐 case 结果

评估报告默认持久化到：

- `data/evals/reports/`

## 4. 当前技术栈

### 后端

- `FastAPI`
- `SQLAlchemy`
- `PostgreSQL`
- `Celery`
- `Redis`
- `LangChain`
- `OpenAI API`

### 向量层

- `FAISS`
- `Milvus`

### 前端

- 原生 `HTML + CSS + JavaScript`
- 与后端同服务部署

## 5. 主要目录结构

```text
app/
  api/                API 路由
  core/               配置、安全、异常、日志、metrics、tracing
  db/                 数据库会话与模型
  frontend/           前端页面与静态资源
  rag/                prompt / retrieval / loader / splitter
  repositories/       数据访问层
  schemas/            Pydantic 模型
  services/           业务服务层
  vectorstores/       FAISS / Milvus 实现
  web/                Web 页面路由
  workers/            Celery 配置与任务
alembic/              数据库迁移
data/
  evals/              RAG 评估数据集
  evals/reports/      RAG 评估历史报告
scripts/              辅助脚本
tests/                测试
```

## 6. 关键文件

### 应用入口

- `app/main.py`
- `app/api/v1/router.py`
- `app/web/router.py`

### 认证与用户

- `app/api/v1/auth.py`
- `app/api/deps.py`
- `app/core/security.py`
- `app/db/models/user.py`
- `app/services/user_service.py`
- `app/repositories/user_repository.py`

### 聊天与检索

- `app/api/v1/chat.py`
- `app/services/chat_service.py`
- `app/services/retrieval_service.py`
- `app/rag/retrieval.py`
- `app/schemas/chat.py`

### 会话

- `app/api/v1/conversations.py`
- `app/services/conversation_service.py`
- `app/repositories/conversation_repository.py`

### 知识库与文档

- `app/api/v1/collections.py`
- `app/api/v1/documents.py`
- `app/services/collection_service.py`
- `app/services/document_service.py`
- `app/services/ingestion_service.py`
- `app/core/path_utils.py`

### 评估体系

- `app/schemas/rag_eval.py`
- `app/services/rag_evaluation_service.py`
- `app/services/rag_evaluation_report_service.py`
- `app/api/v1/rag_evaluations.py`
- `scripts/run_rag_evaluation.py`
- `data/evals/sample_retrieval_eval.json`

### 向量存储

- `app/services/vector_store_service.py`
- `app/vectorstores/faiss_store.py`
- `app/vectorstores/milvus_store.py`
- `scripts/rebuild_vector_indexes.py`

### 可观测性

- `app/core/logging.py`
- `app/core/request_context.py`
- `app/core/metrics.py`
- `app/core/tracing.py`
- `app/core/exceptions.py`
- `app/workers/celery_app.py`
- `app/workers/tasks.py`

### 前端

- `app/frontend/index.html`
- `app/frontend/register.html`
- `app/frontend/evaluations.html`
- `app/frontend/static/app.css`
- `app/frontend/static/app.js`
- `app/frontend/static/register.js`
- `app/frontend/static/evaluations.js`

### 文档

- `README.md`
- `PROJECT_HANDOFF_SUMMARY.md`

## 7. 核心数据流

### 文档入库流程

1. 用户登录
2. 创建或选择知识库
3. 上传文档
4. API 保存原始文件
5. API 在 PostgreSQL 创建 document 记录
6. API 投递 Celery 任务到 Redis
7. Worker 执行 loader / splitter / embedding / vector store 写入
8. 更新 document 状态为 `indexed` 或 `failed`

### 聊天问答流程

1. 用户选择知识库
2. 提交问题
3. 如有需要，先做 Query Rewriting
4. 执行 Hybrid Search
5. 对候选结果做 Reranking
6. 拼接上下文 Prompt
7. 调用 LLM 生成回答
8. 返回完整回答或流式回答
9. 保存 conversation 和 messages

### RAG 评估流程

1. 读取 `data/evals/*.json` 数据集
2. 逐 case 执行真实检索
3. 计算 chunk / document 检索指标
4. 按配置决定是否评估答案质量
5. 按配置决定是否执行 LLM judge
6. 汇总 summary
7. 选择性写入 `data/evals/reports/*.json`
8. 通过 API 或评估看板查看历史报告

### 流式输出事件顺序

当 `POST /api/v1/chat/completions` 传入 `stream=true` 时：

1. `start`
2. 多个 `token`
3. `sources`
4. `done`

## 8. 当前运行方式

### 本地开发模式

1. 启动 PostgreSQL 和 Redis

```powershell
docker compose up -d postgres redis
```

2. 执行数据库迁移

```powershell
alembic upgrade head
```

3. 启动 FastAPI

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

4. 启动 Celery Worker

```powershell
celery -A app.workers.celery_app.celery_app worker --loglevel=INFO --pool=solo
```

5. 打开页面

```text
http://127.0.0.1:8000/
```

### Docker 整站模式

```powershell
docker compose up --build
```

访问地址：

```text
http://127.0.0.1:8080/
```

### 启用 Milvus

```powershell
docker compose --profile milvus up -d etcd minio milvus
```

## 9. 关键环境变量

```env
OBSERVABILITY_LOG_JSON=true
OBSERVABILITY_METRICS_ENABLED=true
OBSERVABILITY_TRACING_ENABLED=false
OBSERVABILITY_SERVICE_NAME=chatrobot-api
OBSERVABILITY_OTLP_ENDPOINT=http://localhost:4318/v1/traces

OPENAI_API_KEY=
OPENAI_BASE_URL=
OPENAI_MODEL=
OPENAI_EMBEDDING_MODEL=
RAG_EVAL_LLM_JUDGE_MODEL=

JWT_SECRET_KEY=
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRES_MINUTES=1440

DATABASE_URL=
DB_AUTO_INIT=false
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=chatrobot
POSTGRES_PASSWORD=chatrobot
POSTGRES_DB=chatrobot

REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=
CELERY_RESULT_BACKEND=

VECTOR_BACKEND=faiss
RAG_USE_HYBRID_SEARCH=true
RAG_USE_RERANK=true
RAG_QUERY_REWRITE_ENABLED=true

MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_COLLECTION=chatrobot_documents
```

## 10. 当前 API 重点

### 公开接口

- `GET /`
- `GET /register`
- `GET /evaluations`
- `GET /api/v1/health`
- `GET /metrics`
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`

### 受保护接口

- `GET /api/v1/auth/me`
- `GET /api/v1/collections`
- `POST /api/v1/collections`
- `POST /api/v1/collections/{collection_id}/ingest`
- `POST /api/v1/documents/upload`
- `GET /api/v1/documents`
- `GET /api/v1/documents/{document_id}`
- `POST /api/v1/documents/{document_id}/retry`
- `DELETE /api/v1/documents/{document_id}`
- `GET /api/v1/conversations`
- `GET /api/v1/conversations/{conversation_id}`
- `POST /api/v1/chat/completions`
- `GET /api/v1/evaluations/rag/datasets`
- `GET /api/v1/evaluations/rag/reports`
- `GET /api/v1/evaluations/rag/reports/{report_id}`
- `POST /api/v1/evaluations/rag/run`

## 11. 当前测试状态

已覆盖的测试包括：

- 认证 API
- 健康检查 API
- 知识库 API / service
- 文档 API
- 会话 API / service
- 聊天 API / service
- 检索增强 service
- RAG 评估 service
- RAG 评估报告 service
- RAG 评估 API
- Web 页面
- 向量服务选择
- 文档路径兼容策略
- 可选 Milvus 集成测试

最近一次完整验证通过：

- `node --check app\frontend\static\evaluations.js`
- `node --check app\frontend\static\app.js`
- `python -m compileall app scripts tests`
- `python scripts\run_rag_evaluation.py --help`
- `python -m pytest`

结果：

- `66 passed, 1 skipped`

## 12. 当前已知限制

- JWT 目前只有 access token，还没有 refresh token
- 还没有“退出即失效”的 token 黑名单机制
- 当前 Rerank 还是启发式重排，不是外部专用 reranker 模型
- Query Rewriting 依赖当前聊天 LLM，而不是独立轻量模型
- RAG 评估的回答质量默认还是启发式为主，LLM judge 是可选模式
- 评估看板当前以“单次报告查看”为主，还没有趋势对比图表
- 历史报告当前保存在本地文件系统，还没有入库或对象存储
- 老数据如果缺少 `owner_id`，不会自动归属到新用户
- Windows 终端下 `README.md` / 本交接文档可能因控制台编码显示乱码，但文件本身为 UTF-8

## 13. 建议下一步优先级

### 第一优先级

1. 评估报告趋势分析
2. 评估看板图表化展示
3. refresh token
4. 退出登录失效机制

### 第二优先级

1. 更强的模型式 Rerank
2. LLM judge 与启发式分数的趋势对比
3. 评估报告导出 / 对比
4. 多端会话管理

### 第三优先级

1. 密码修改与重置
2. Celery task 更细粒度测试
3. Milvus 真联调测试增强
4. 评估报告入库或对象存储

### 第四优先级

1. Nginx 反向代理
2. HTTPS 与域名
3. 更完整的 tracing 落地
4. 正式生产部署编排

## 14. 下一轮对话可直接复制的上下文

```text
请基于 D:\Dify\LangChain\ChatRobot_v3 项目继续开发。

项目当前状态：
- FastAPI + PostgreSQL + SQLAlchemy
- JWT 用户系统已完成
- Swagger OAuth2 登录已兼容
- Celery + Redis 异步文档入库已完成
- FAISS / Milvus 双后端已完成
- Alembic 已接入
- 前端已完成登录/注册、知识库、文档上传、文档状态、会话历史和聊天工作台
- 当前工作台布局为左右等高主框架，右侧回答区更大，左右列表均支持独立滚动
- /api/v1/chat/completions 已支持 stream=true 的 SSE 流式输出
- 前端已支持 token 级实时渲染和来源延迟回填
- 当前已补齐结构化日志、request id middleware、API latency logging、Celery task logging、Prometheus /metrics、OpenTelemetry tracing 接入点、错误审计日志
- 当前已补齐 RAG 评估体系，覆盖检索指标、回答质量、groundedness 和可选 LLM judge
- 当前已新增 RAG 评估报告 API：/api/v1/evaluations/rag/datasets、/reports、/reports/{report_id}、/run
- 当前已新增评估看板页面 /evaluations，并支持历史报告查看
- 当前交接文档见 PROJECT_HANDOFF_SUMMARY.md 和 README.md

请先阅读：
1. README.md
2. PROJECT_HANDOFF_SUMMARY.md
3. app/services/chat_service.py
4. app/frontend/static/app.js
5. app/services/rag_evaluation_service.py
6. app/services/rag_evaluation_report_service.py
7. app/frontend/static/evaluations.js

然后继续做：
[把你下一步要做的任务写在这里]
```
