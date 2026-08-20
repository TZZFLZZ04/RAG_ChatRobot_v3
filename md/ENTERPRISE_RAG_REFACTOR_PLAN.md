# ChatRobot_v3 企业级 RAG 重构方案

## 1. 当前项目现状

当前项目是一个单文件 LangChain CLI RAG Demo，主文件为：

- `ChatRobot_v3.0.py`

当前核心流程：

1. 从 `OneFlower/` 目录加载文档。
2. 使用 `PyPDFLoader`、`Docx2txtLoader`、`TextLoader` 加载 PDF、Word、TXT。
3. 使用 `RecursiveCharacterTextSplitter` 切分文本。
4. 使用 `OpenAIEmbeddings` 生成 embedding。
5. 使用 `Qdrant.from_documents(location=":memory:")` 创建内存向量库。
6. 使用 `ChatOpenAI` 创建 LLM。
7. 使用 `ConversationSummaryMemory` 管理对话记忆。
8. 使用 `ConversationalRetrievalChain` 完成检索增强问答。
9. 通过命令行 `input()` 进行交互。

当前主要问题：

- API Key 硬编码在代码中，有严重安全风险。
- 单文件结构，不利于维护、测试和扩展。
- 向量库是内存模式，程序重启后索引丢失。
- 没有 FastAPI 服务层，无法作为后端服务提供接口。
- 没有数据库、用户、会话、权限、日志、监控、测试、CI/CD。
- 没有文档入库接口和异步任务机制。
- 没有统一配置管理。
- 没有工程化目录结构。
- 没有环境隔离、Docker、部署方案。

---

## 2. 重构目标

目标是将当前 Demo 重构为一个勉强达到企业级要求的 RAG 后端项目，技术栈建议如下：

- Web 框架：`FastAPI`
- ASGI Server：`Uvicorn` 或 `Gunicorn + UvicornWorker`
- RAG 框架：`LangChain` 或 `LlamaIndex`
- 向量检索：`FAISS` 本地检索 + `Milvus` 生产级向量数据库
- Embedding 模型：`OpenAIEmbeddings`、`bge-large-zh-v1.5`、`bge-m3` 或企业内部 embedding 服务
- LLM：`ChatOpenAI`、`Azure OpenAI`、本地大模型服务或 OpenAI 兼容 API
- 元数据数据库：`PostgreSQL`
- 缓存和任务队列：`Redis`
- 异步任务：`Celery` 或 `RQ`
- 配置管理：`pydantic-settings`
- 日志：`loguru` 或标准库 `logging`
- 鉴权：`JWT Bearer Token`
- 测试：`pytest`
- 代码质量：`ruff`、`black`、`mypy`
- 容器化：`Docker`、`docker-compose`
- 部署：`Nginx + Gunicorn/Uvicorn + Docker Compose`，后续可迁移到 Kubernetes

---

## 3. 推荐项目目录结构

建议将项目重构为如下结构：

```text
ChatRobot_v3/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── router.py
│   │       ├── chat.py
│   │       ├── documents.py
│   │       ├── collections.py
│   │       └── health.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── logging.py
│   │   ├── security.py
│   │   └── exceptions.py
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── chat.py
│   │   ├── document.py
│   │   ├── collection.py
│   │   └── common.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── chat_service.py
│   │   ├── document_service.py
│   │   ├── embedding_service.py
│   │   ├── retrieval_service.py
│   │   ├── vector_store_service.py
│   │   └── ingestion_service.py
│   ├── rag/
│   │   ├── __init__.py
│   │   ├── loaders.py
│   │   ├── splitters.py
│   │   ├── retrievers.py
│   │   ├── rerankers.py
│   │   ├── chains.py
│   │   └── prompts.py
│   ├── vectorstores/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── faiss_store.py
│   │   └── milvus_store.py
│   ├── db/
│   │   ├── __init__.py
│   │   ├── session.py
│   │   ├── base.py
│   │   └── models/
│   │       ├── __init__.py
│   │       ├── user.py
│   │       ├── document.py
│   │       ├── collection.py
│   │       ├── conversation.py
│   │       └── message.py
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── document_repository.py
│   │   ├── collection_repository.py
│   │   └── conversation_repository.py
│   ├── workers/
│   │   ├── __init__.py
│   │   ├── celery_app.py
│   │   └── tasks.py
│   └── utils/
│       ├── __init__.py
│       ├── file_utils.py
│       └── id_utils.py
├── data/
│   ├── raw/
│   ├── processed/
│   └── faiss_indexes/
├── tests/
│   ├── test_chat_api.py
│   ├── test_document_api.py
│   └── test_retrieval_service.py
├── scripts/
│   ├── ingest_documents.py
│   └── create_milvus_collection.py
├── docker/
│   └── nginx.conf
├── .env.example
├── .gitignore
├── requirements.txt
├── docker-compose.yml
├── Dockerfile
└── README.md
```

---

## 4. 分阶段操作步骤

### 阶段一：安全整改和基础工程化

目标：先把单文件 Demo 拆开，移除硬编码密钥。

操作步骤：

1. 新建 `.env.example`，保存环境变量模板。
2. 新建 `app/core/config.py`，使用 `pydantic-settings` 读取配置。
3. 将 `OPENAI_API_KEY`、`OPENAI_BASE_URL` 从代码中删除，改为环境变量读取。
4. 新建 `requirements.txt`，固定依赖版本。
5. 新建 `app/main.py`，作为 FastAPI 入口。
6. 将文档加载、文本切分、embedding、vectorstore、chat chain 拆成多个 service。
7. 保留原始 `ChatRobot_v3.0.py` 作为 legacy demo，或迁移后删除。

建议环境变量：

```env
APP_NAME=ChatRobot Enterprise RAG
APP_ENV=dev
APP_DEBUG=true

OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small

VECTOR_BACKEND=faiss
FAISS_INDEX_DIR=./data/faiss_indexes

MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_COLLECTION=chatrobot_documents

POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=chatrobot
POSTGRES_PASSWORD=chatrobot
POSTGRES_DB=chatrobot

REDIS_URL=redis://localhost:6379/0
JWT_SECRET_KEY=replace_me
JWT_ALGORITHM=HS256
```

---

### 阶段二：引入 FastAPI 服务层

目标：从 CLI 对话变成 HTTP API 服务。

建议接口：

```text
GET    /api/v1/health
POST   /api/v1/chat/completions
POST   /api/v1/documents/upload
GET    /api/v1/documents
GET    /api/v1/documents/{document_id}
DELETE /api/v1/documents/{document_id}
POST   /api/v1/collections
GET    /api/v1/collections
POST   /api/v1/collections/{collection_id}/ingest
```

核心请求模型变量名建议：

- `ChatRequest`
- `ChatResponse`
- `DocumentUploadResponse`
- `CollectionCreateRequest`
- `CollectionResponse`
- `SourceDocument`
- `RetrievedChunk`

`ChatRequest` 建议字段：

```python
class ChatRequest(BaseModel):
    query: str
    conversation_id: str | None = None
    collection_id: str
    top_k: int = 5
    use_rerank: bool = False
    stream: bool = False
```

`ChatResponse` 建议字段：

```python
class ChatResponse(BaseModel):
    answer: str
    conversation_id: str
    sources: list[SourceDocument]
    token_usage: dict | None = None
```

---

### 阶段三：设计 RAG 数据流

推荐 RAG 数据流：

```text
用户上传文件
  -> 文件落盘 data/raw
  -> 记录 document metadata 到 PostgreSQL
  -> Celery 异步解析文件
  -> loader 加载文档
  -> splitter 切 chunk
  -> embedding service 生成向量
  -> FAISS 或 Milvus 写入向量
  -> 更新 document 状态为 indexed

用户提问
  -> FastAPI 接收 ChatRequest
  -> 查询 conversation history
  -> query rewrite，可选
  -> embedding query
  -> vectorstore similarity search
  -> rerank，可选
  -> 拼装 prompt
  -> 调用 LLM
  -> 保存 message
  -> 返回 answer + sources
```

建议关键变量名：

- `document_id`
- `collection_id`
- `conversation_id`
- `message_id`
- `chunk_id`
- `source_path`
- `source_name`
- `chunk_text`
- `chunk_index`
- `embedding_vector`
- `metadata`
- `top_k`
- `score_threshold`
- `retrieved_chunks`
- `reranked_chunks`
- `context_text`
- `system_prompt`
- `user_prompt`

---

### 阶段四：FAISS + Milvus 双后端设计

建议定义统一抽象接口：

```python
class VectorStoreBackend(Protocol):
    def add_documents(self, chunks: list[DocumentChunk]) -> None:
        ...

    def similarity_search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        ...

    def delete_by_document_id(self, document_id: str) -> None:
        ...
```

使用方式：

- 开发环境：`VECTOR_BACKEND=faiss`
- 单机小规模：`FAISS`
- 生产环境：`VECTOR_BACKEND=milvus`
- 大规模、多租户、高并发：`Milvus`

FAISS 适合：

- 本地开发
- 小数据量
- 快速验证
- 无服务依赖

Milvus 适合：

- 企业生产
- 大数据量
- 多 collection
- 高并发查询
- 水平扩展
- 更完善的索引和过滤能力

Milvus collection 字段建议：

```text
id: VarChar, primary key
collection_id: VarChar
document_id: VarChar
chunk_id: VarChar
chunk_index: Int64
text: VarChar
source_name: VarChar
source_path: VarChar
metadata_json: JSON
embedding: FloatVector(dim=1536 或 1024 或 768)
created_at: Int64
```

注意：`embedding` 的 `dim` 必须和 embedding 模型输出维度一致。

---

### 阶段五：引入 PostgreSQL 元数据管理

建议数据库表：

#### users

- `id`
- `username`
- `email`
- `hashed_password`
- `is_active`
- `created_at`
- `updated_at`

#### collections

- `id`
- `name`
- `description`
- `owner_id`
- `vector_backend`
- `created_at`
- `updated_at`

#### documents

- `id`
- `collection_id`
- `filename`
- `file_path`
- `file_type`
- `file_size`
- `status`
- `chunk_count`
- `error_message`
- `created_at`
- `updated_at`

`status` 可选值：

- `uploaded`
- `processing`
- `indexed`
- `failed`
- `deleted`

#### conversations

- `id`
- `user_id`
- `collection_id`
- `title`
- `created_at`
- `updated_at`

#### messages

- `id`
- `conversation_id`
- `role`
- `content`
- `sources_json`
- `token_usage_json`
- `created_at`

---

### 阶段六：异步文档入库

企业级项目不建议在上传接口中直接完成解析、embedding 和入库，因为这些步骤耗时较长。

建议使用：

- `Redis` 作为 broker
- `Celery` 作为任务队列
- `ingest_document_task` 作为异步任务

任务函数建议：

```python
@celery_app.task(name="ingest_document_task")
def ingest_document_task(document_id: str) -> None:
    ...
```

任务流程：

1. 根据 `document_id` 查询文档元数据。
2. 将文档状态改为 `processing`。
3. 加载文件。
4. 切分 chunk。
5. 生成 embedding。
6. 写入 FAISS 或 Milvus。
7. 更新文档状态为 `indexed`。
8. 如果异常，更新状态为 `failed` 并保存 `error_message`。

---

### 阶段七：Prompt、检索和生成优化

基础 RAG Prompt 建议：

```text
你是一个企业知识库问答助手。
请只基于给定的上下文回答用户问题。
如果上下文中没有答案，请明确回答“根据现有资料无法确定”。
不要编造事实。

上下文：
{context}

用户问题：
{question}
```

可增强能力：

- Query Rewrite：根据历史对话改写用户问题。
- Hybrid Search：关键词检索 + 向量检索。
- Rerank：使用 `bge-reranker-large` 或 Cohere Rerank。
- Score Threshold：过滤低相似度 chunk。
- Context Compression：压缩过长上下文。
- Citation：返回引用来源和 chunk。
- Streaming：通过 SSE 流式返回回答。

建议核心参数：

```env
RAG_CHUNK_SIZE=500
RAG_CHUNK_OVERLAP=80
RAG_TOP_K=5
RAG_SCORE_THRESHOLD=0.3
RAG_USE_RERANK=false
RAG_MAX_CONTEXT_CHARS=8000
```

---

### 阶段八：工程化和企业级能力

#### 配置管理

使用 `pydantic-settings`：

- `Settings`
- `get_settings()`
- `.env`
- `.env.example`

#### 日志

日志字段建议：

- `request_id`
- `user_id`
- `conversation_id`
- `document_id`
- `collection_id`
- `latency_ms`
- `error_type`

#### 错误处理

定义统一响应：

```json
{
  "code": "DOCUMENT_NOT_FOUND",
  "message": "Document not found",
  "request_id": "..."
}
```

#### 鉴权

建议：

- `POST /api/v1/auth/login`
- `POST /api/v1/auth/register`
- JWT Access Token
- `get_current_user`
- collection 级别权限控制

#### 测试

至少覆盖：

- 健康检查接口
- 文档上传接口
- 文档入库任务
- 检索服务
- Chat API
- VectorStoreBackend 抽象实现

#### CI/CD

建议流程：

1. 安装依赖。
2. 运行 `ruff check`。
3. 运行 `black --check`。
4. 运行 `pytest`。
5. 构建 Docker 镜像。
6. 推送镜像。
7. 部署到服务器。

---

## 5. 推荐依赖 requirements.txt

初版可使用：

```txt
fastapi
uvicorn[standard]
pydantic
pydantic-settings
python-dotenv
python-multipart
sqlalchemy
alembic
psycopg2-binary
redis
celery
langchain
langchain-openai
langchain-community
openai
faiss-cpu
pymilvus
pypdf
docx2txt
tiktoken
loguru
python-jose[cryptography]
passlib[bcrypt]
pytest
httpx
ruff
black
mypy
```

如果使用国产/本地 embedding，可追加：

```txt
sentence-transformers
torch
transformers
```

---

## 6. docker-compose 建议服务

建议包含：

- `api`: FastAPI 服务
- `worker`: Celery Worker
- `postgres`: 元数据数据库
- `redis`: 缓存和任务队列
- `milvus`: 向量数据库
- `minio`: Milvus 对象存储依赖或文档对象存储
- `etcd`: Milvus 依赖
- `nginx`: 反向代理，可选

服务变量名建议：

- `chatrobot-api`
- `chatrobot-worker`
- `chatrobot-postgres`
- `chatrobot-redis`
- `chatrobot-milvus`
- `chatrobot-minio`
- `chatrobot-etcd`

---

## 7. 推荐实施顺序

建议不要一次性全部重写，而是按以下顺序推进：

1. **备份当前项目**：保留 `ChatRobot_v3.0.py`。
2. **创建工程目录**：新建 `app/`、`tests/`、`data/`、`scripts/`。
3. **迁移配置**：创建 `.env.example` 和 `app/core/config.py`。
4. **创建 FastAPI 入口**：实现 `/api/v1/health`。
5. **拆分 RAG 模块**：把 loader、splitter、embedding、retriever、chain 拆出去。
6. **实现 FAISS 后端**：先跑通本地持久化索引。
7. **实现 Chat API**：完成 `POST /api/v1/chat/completions`。
8. **实现文档上传 API**：先同步入库，再改异步。
9. **加入 PostgreSQL**：管理 document、collection、conversation、message。
10. **加入 Celery + Redis**：异步处理文档入库。
11. **加入 Milvus 后端**：实现生产级向量库。
12. **加入鉴权**：JWT、用户、权限。
13. **加入日志、测试、Docker**。
14. **进行压测和部署优化**。

---

## 8. 后续可以向 AI 提问的 Prompt 模板

### 让 AI 生成项目骨架

```text
请基于以下技术栈帮我生成一个企业级 RAG 项目骨架：FastAPI、LangChain、FAISS、Milvus、PostgreSQL、Redis、Celery、pydantic-settings、Docker。
请按照我提供的目录结构创建文件，并先实现 health check、配置管理、日志模块和统一异常处理。
```

### 让 AI 迁移当前单文件代码

```text
我现在有一个单文件 LangChain RAG Demo，文件名是 ChatRobot_v3.0.py。
它使用 PyPDFLoader、Docx2txtLoader、TextLoader、RecursiveCharacterTextSplitter、OpenAIEmbeddings、Qdrant、ChatOpenAI、ConversationSummaryMemory、ConversationalRetrievalChain。
请帮我将它重构为 FastAPI 项目，拆分为 loader、splitter、embedding_service、vector_store_service、retrieval_service、chat_service。
```

### 让 AI 实现 FAISS 后端

```text
请帮我实现一个 FAISSVectorStoreBackend。
要求支持 add_documents、similarity_search、delete_by_document_id、save_local、load_local。
文档 chunk 需要包含 document_id、collection_id、chunk_id、chunk_index、source_name、source_path、metadata。
```

### 让 AI 实现 Milvus 后端

```text
请帮我实现一个 MilvusVectorStoreBackend。
要求使用 pymilvus，collection 字段包括 id、collection_id、document_id、chunk_id、chunk_index、text、source_name、source_path、metadata_json、embedding、created_at。
需要支持 collection 初始化、插入向量、相似度搜索、按 document_id 删除。
```

### 让 AI 实现文档上传和异步入库

```text
请帮我实现 FastAPI 文档上传接口和 Celery 异步入库任务。
上传接口保存文件到 data/raw，写入 PostgreSQL documents 表，状态为 uploaded，然后投递 ingest_document_task(document_id)。
Celery 任务负责解析文件、切 chunk、生成 embedding、写入 FAISS 或 Milvus，并更新 document 状态。
```

### 让 AI 实现 Chat API

```text
请帮我实现 POST /api/v1/chat/completions。
请求体包含 query、conversation_id、collection_id、top_k、use_rerank、stream。
接口需要调用 retrieval_service 检索上下文，调用 chat_service 生成回答，保存 conversation message，并返回 answer、conversation_id、sources、token_usage。
```

---

## 9. 最小可行版本 MVP 范围

如果时间有限，建议先做 MVP：

- FastAPI 服务
- `.env` 配置
- 文档上传
- FAISS 本地持久化
- Chat API
- 基础 RAG Prompt
- 返回 sources
- 简单日志
- Dockerfile

暂缓：

- Milvus
- PostgreSQL
- Celery
- JWT
- Rerank
- Streaming
- 多租户
- Kubernetes

MVP 完成后，再逐步补齐企业级能力。

---

## 10. 重要注意事项

1. 不要再硬编码 `OPENAI_API_KEY`。
2. 不要在生产环境使用内存向量库。
3. Embedding 模型维度必须和 FAISS/Milvus index 维度一致。
4. 文档入库应尽量异步化。
5. RAG 必须返回 sources，否则企业场景难以追溯。
6. 上传文件需要限制大小和类型。
7. 用户输入需要做长度限制和安全校验。
8. LLM 调用需要超时、重试和错误处理。
9. 日志不要打印 API Key、密码、Token。
10. 生产部署前必须补测试、鉴权、日志和监控。

---

## 11. 关键词汇总

框架和组件：

- `FastAPI`
- `Uvicorn`
- `LangChain`
- `LlamaIndex`
- `FAISS`
- `Milvus`
- `PostgreSQL`
- `Redis`
- `Celery`
- `SQLAlchemy`
- `Alembic`
- `pydantic-settings`
- `Docker`
- `docker-compose`
- `Nginx`
- `pytest`
- `ruff`
- `black`
- `mypy`

RAG 相关：

- `Document Loader`
- `Text Splitter`
- `Embedding Model`
- `Vector Store`
- `Retriever`
- `Reranker`
- `Prompt Template`
- `Conversational Retrieval`
- `Query Rewrite`
- `Hybrid Search`
- `Score Threshold`
- `Context Compression`
- `Citation`
- `Source Documents`

核心变量名：

- `document_id`
- `collection_id`
- `conversation_id`
- `message_id`
- `chunk_id`
- `chunk_index`
- `chunk_text`
- `embedding_vector`
- `metadata`
- `top_k`
- `score_threshold`
- `retrieved_chunks`
- `reranked_chunks`
- `context_text`
- `system_prompt`
- `user_prompt`
- `source_name`
- `source_path`

推荐类名：

- `Settings`
- `ChatRequest`
- `ChatResponse`
- `SourceDocument`
- `RetrievedChunk`
- `DocumentChunk`
- `DocumentService`
- `EmbeddingService`
- `RetrievalService`
- `ChatService`
- `IngestionService`
- `VectorStoreBackend`
- `FAISSVectorStoreBackend`
- `MilvusVectorStoreBackend`
- `DocumentRepository`
- `CollectionRepository`
- `ConversationRepository`

---

## 12. 一句话总结

当前项目可以作为 RAG 原型保留，但要达到企业级，需要从“单文件 CLI + 内存向量库”重构为“FastAPI 服务 + 模块化 RAG Pipeline + 持久化向量库 + 元数据数据库 + 异步入库 + 配置/日志/测试/鉴权/Docker”的工程化后端项目。
