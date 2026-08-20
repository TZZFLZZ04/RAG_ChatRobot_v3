# 发现与决策

## 需求
- 审查并重构 ChatRobot 代码。
- 参考 `AGENTS_a_c.md`。
- 使用 `grill-me`、`karpathy-guidelines`、`planning-with-files-zh`。
- 采用逐步更新方式，先确认重点范围。
- 首批重点关注 RAG 检索模块；暂不扩展到文档入库、生成回答、认证或前端。
- 目标是通过递归切分、语义切分、混合检索和上下文感知检索，提高 RAG 回答正确率。
- 切分策略天然位于入库/索引链路，因此允许检查与切分直接相关的入库代码，但不扩展到无关文档管理逻辑。
- 第一批实现范围进一步缩小为递归切分；语义切分、混合检索和上下文感知检索保留为后续阶段。
- 本对话仅讨论、审查并编写修改方案；业务代码优化由用户另开对话实施。
- 基于桌面 PDF《50个顶级的DeepSeek学术论文指令，强烈建议收藏！》创建项目可用的评测数据集和操作说明。

## 研究发现
- 项目是 Python 3.11 FastAPI RAG 应用，包含 API、Service、Repository、RAG、向量存储、Celery 和静态前端。
- 架构约束：路由保持轻量；业务编排放在 `services/`；数据库查询封装在 `repositories/`；依赖注入集中在 `app/api/deps.py`。
- 测试使用 Pytest；API 测试优先依赖覆盖和轻量 fake；Milvus 集成测试可能需要独立基础设施。
- 数据库结构变化必须通过 Alembic；不得提交敏感配置或运行数据。
- 当前工作目录下没有可被 Git 识别的仓库元数据。
- 最新仓库规范取代此前 AGENTS 指令；新增或修复行为必须补充相应测试，Python 新代码使用类型注解和 `from __future__ import annotations`。
- 用户明确术语为“上下文感知检索”，并明确它不是对话历史查询改写。
- `app/rag/splitters.py` 已使用 LangChain 的 `RecursiveCharacterTextSplitter`。
- `app/services/ingestion_service.py` 的文档入库路径统一调用 `split_documents()`，并传入 `rag_chunk_size` 与 `rag_chunk_overlap`。
- `app/core/config.py` 已提供 `RAG_CHUNK_SIZE`（默认 500）和 `RAG_CHUNK_OVERLAP`（默认 80）。
- 当前切分器使用库默认分隔符，没有显式覆盖中文句号、问号、感叹号等分隔层级。
- 尚未发现针对 `app/rag/splitters.py` 的独立单元测试；现有测试只 fake 掉切分函数以验证路径处理。
- `requirements.txt` 对 `langchain-text-splitters` 未固定版本，方案不应依赖未经确认的新版本 API。
- 当前已安装切分器构造函数支持 `separators`、`keep_separator` 和 `is_separator_regex`；默认分隔符为 `['\n\n', '\n', ' ', '']`。
- `.env.example` 已公开 `RAG_CHUNK_SIZE=500` 与 `RAG_CHUNK_OVERLAP=80`，README 未检索到对应配置说明。
- `DocumentChunk` 保存文档/集合/块标识、原文、来源路径和 metadata；递归切分方案需要保持这些字段与连续 `chunk_index`。
- 本地样例显示：默认分隔符会把中文“请提前三天提交申请”截成两块；加入中英文句末标点并设置 `keep_separator="end"` 后，优先形成完整句子块。
- 当前相关基线测试 `python -m pytest tests/test_document_path_strategy.py -q` 结果为 3 passed；另有 1 条来自 Starlette `python_multipart` 导入方式的无关警告。
- 项目现有 RAG 评测已提供 Precision@K、Recall@K、Hit Rate@K、MRR@K、Average Precision@K、nDCG@K、来源命中率、回答 groundedness、总体回答分和延迟指标，可直接用于切分策略前后对比。
- README 已有“RAG 检索增强”和“RAG 评估体系”章节，但当前未说明 `RAG_CHUNK_SIZE`、`RAG_CHUNK_OVERLAP` 及修改切分策略后需要重建索引。

## 技术决策
| 决策 | 理由 |
|------|------|
| 在用户明确范围前不检查或修改业务代码 | 避免无边界审查和过度重构 |
| 先建立测试基线，再做最小改动 | 符合可验证、外科式修改原则 |
| 首批审查范围限定为 RAG 检索链路 | 用户已明确范围，避免无关重构 |
| 将与切分直接相关的入库链路纳入候选范围 | 切分无法仅在查询时检索模块内实现 |
| 上下文感知检索采用索引时块级前缀 | 用户提供的流程图明确了实现语义 |
| 首先基线审查并尝试递归切分 | 用户明确要求先采用该方法，其他增强暂缓 |
| 候选最小改动聚焦中文友好分隔符与单元测试 | 递归切分本身已存在，重复实现会增加无效变更 |
| 本对话不修改业务代码 | 用户明确将后续代码优化放入另一个对话 |
| 不把结构性切分测试等同于回答正确率提升 | 正确率结论必须来自同一数据集的修改前后检索/回答评测 |

## 递归切分修改方案（供后续实现对话）

### 范围
- 修改 `app/rag/splitters.py`：保留现有公开函数签名，仅完善递归分隔符配置。
- 新增 `tests/test_splitters.py`：覆盖项目自己的切分配置和 `DocumentChunk` 映射逻辑。
- 更新 `README.md`：说明切分配置、字符语义和重新索引要求。
- 不修改 loader、ingestion service、vector store、数据库模型、API 或环境变量名称。

### 建议设计
1. 在 `app/rag/splitters.py` 定义模块级递归分隔符常量，按从强到弱的语义边界排列：空行、换行、中文句末标点、英文句末标点、分号、逗号、空格、空字符串兜底；同时兼容 CRLF 与 LF。
2. `build_text_splitter()` 继续接收 `chunk_size` 和 `chunk_overlap`，向 `RecursiveCharacterTextSplitter` 传入上述分隔符，并设置 `keep_separator="end"`，使句末标点留在前一个块。
3. `split_documents()` 的参数、`DocumentChunk` 字段、metadata 复制、`chunk_id` 和 `chunk_index` 逻辑保持不变。
4. 不增加“切分策略”配置开关；当前阶段只有一种已确认策略，新增开关会制造未使用复杂度。

### 建议测试
- `test_recursive_splitter_prefers_chinese_sentence_boundaries`：中文长段落应优先在 `。！？` 后切分，不能在仍有合适句界时截断句子。
- `test_recursive_splitter_prefers_english_sentence_boundaries`：英文应优先在句末标点后切分。
- `test_recursive_splitter_falls_back_for_unbroken_text`：无空格、无标点的长文本仍能逐字符兜底，且每块不超过 `chunk_size`。
- `test_split_documents_preserves_metadata_and_assigns_deterministic_ids`：保留 loader metadata，并在同一输入与配置下生成连续 `chunk_index` 和确定性的 `{document_id}-{index}` 标识。
- 不测试 LangChain 内部实现；只断言本项目承诺的边界、大小和映射行为。

### 质量验收
- 结构验收：新增切分器单测通过，现有入库路径测试通过，全量测试无新增失败。
- 检索验收：使用同一份已标注评测集，在相同检索配置下比较修改前后 Hit Rate@K、MRR@K、nDCG@K；至少不得回退，并记录中文长段落样本的变化。
- 回答验收：在固定模型与 prompt 下比较 groundedness 和 overall answer score；仅当评测提升时才宣称回答正确率改善。
- 性能验收：记录 chunk 数量、索引耗时和平均/P95 检索延迟，防止更细边界导致块数量异常膨胀。
- 重切分会改变基于顺序的 `chunk_id`；前后对比应优先使用 document/source 级标签，若必须比较 chunk 指标则需重新标注相关 chunk ID。

### 后续实现顺序
1. 先新增失败的中文/英文边界测试，确认当前默认分隔符无法满足预期。
2. 仅修改切分器构造参数，使新增测试通过。
3. 运行切分器测试和现有入库路径测试。
4. 重建同一测试语料的索引，运行现有 RAG 评测并保存前后报告。
5. 更新 README，最后运行全量测试。

### 后续实现对话的验证命令
```powershell
python -m pytest tests/test_splitters.py -q
python -m pytest tests/test_document_path_strategy.py -q
python -m pytest tests/test_retrieval_service.py tests/test_rag_evaluation_service.py -q
python -m pytest
```

索引与评测建议先限定单个评测文档或集合：
```powershell
python scripts/rebuild_vector_indexes.py --backend faiss --document-id <document_id>
python scripts/run_rag_evaluation.py --dataset <fixed_dataset.json> --answer-mode generate --use-hybrid-search true --use-rerank true --output data/evals/reports/after_recursive_split.json
```

修改前需用完全相同的数据集、模型、Top-K、混合检索与重排设置生成 `before_recursive_split.json`。若生产使用 Milvus，再对 Milvus 后端重复重建和验证。

### 重建与发布注意事项
- `scripts/rebuild_vector_indexes.py` 已复用 `IngestionService`，无需新建迁移脚本或重建入口。
- 该脚本会先删除目标文档旧索引；先使用 `--document-id` 对可恢复的评测文档试跑，再扩展到 `--collection-id` 或全量。
- FAISS 与 Milvus 均需分别重建实际使用的索引；不要只修改代码后继续使用旧索引评测。
- `chunk_size` 当前按 Python 字符长度计算，不是模型 token 数；README 应明确这一点，并说明 `chunk_overlap < chunk_size`。

### 明确排除
- 不在本批引入语义切分、LLM 上下文前缀、BM25/RRF 调整或 reranker 调参。
- 不更改现有函数签名、环境变量名称、API、数据库 schema 或向量存储 schema。
- 不顺手处理 Starlette 的无关弃用警告或未锁版本的全局依赖治理。

## 遇到的问题
| 问题 | 解决方案 |
|------|---------|
| 首次读取中文文档乱码且输出截断 | 使用 UTF-8 分段读取完成 |
| 本地目录不是 Git 仓库 | 暂以本地文件为准；待范围确认后再判断是否需 GitHub 仓库上下文 |
| Starlette 测试出现 `python_multipart` PendingDeprecationWarning | 与递归切分无关，记录但不纳入方案 |

## 资源
- `AGENTS_a_c.md`
- 用户提供的仓库贡献指南

## 视觉/浏览器发现
- 用户提供的流程图展示：原始文档先分块；LLM 为每个分块生成上下文前缀，图中标注可使用 prompt caching；随后将“前缀 + 原文块”写入索引。
- 图中引用的效果说明为：加入 BM25 后检索失败率下降 49%，再加入重排后下降 67%；这些数字是图中引用的 Anthropic 数据，尚未作为本项目验收目标。

---
*每执行2次查看/浏览器/搜索操作后更新此文件*

## 2026-08-17 Google Cloud 部署就绪审计
- 审计进行中；本轮只读检查应用与基础设施配置，不修改业务代码或云资源。
- 目标输出：区分“必须补齐才能上线”“生产环境强烈建议”“按规模可选”的配置与操作。
- 仓库已有 `Dockerfile`、`docker-compose.yml`、`.env.example`、Alembic、FastAPI、Celery、PostgreSQL、Redis，以及 FAISS/Milvus 两种向量后端，具备容器化部署基础。
- 根目录存在本地 `.env`，部署时必须确保它不进入镜像或源码包；当前虽有 `.git` 目录，但 `git status` 无法识别为仓库，不能依赖 Git 状态确认敏感文件是否被跟踪。
- `Dockerfile` 确实执行 `COPY . .`，且项目没有 `.dockerignore`：会把 `.env`、`data/`、`venv/`、测试与临时 PDF 等构建上下文复制到镜像，这是上线前必须修复的密钥泄露、镜像膨胀和数据泄露风险。
- Compose 将 API(8080)、PostgreSQL(5432)、Redis(6379)、Milvus/MinIO 管理端口直接发布到宿主机；云防火墙若放行会暴露内部服务。生产只应公开 HTTPS 入口，数据库/缓存/向量库保留私网或 loopback。
- Compose 使用固定弱口令 `chatrobot`、`minioadmin`，Redis 无认证；这些默认值不能用于公网生产。
- Redis 没有持久化卷；Celery 结果和队列在实例/容器重启时可丢失。评估进度依赖 `CELERY_TASK_IGNORE_RESULT=false` 与结果后端。
- `requirements.txt` 全部未固定版本且包含 `pytest`；生产构建不可复现，也把开发依赖装入运行镜像。至少应锁定已验证版本，理想上拆分运行/开发依赖并使用非 root 用户、多阶段或最小镜像。
- 应用生产配置需显式设置 `APP_ENV=prod`、`APP_DEBUG=false`、强随机 `JWT_SECRET_KEY`、真实 `OPENAI_API_KEY`、数据库/Redis/向量库连接，以及 `DB_AUTO_INIT=false` 后单独执行 `alembic upgrade head`。
- 当前 `/api/v1/health` 只回报静态“ok”，不探测 PostgreSQL、Redis、向量后端或可写存储；可作存活探针，不能作为可靠就绪探针。
- `/metrics` 在启用时无鉴权且由公网应用直接暴露；生产应仅允许监控系统访问，或经代理限制路径。
- 文件上传、FAISS 索引与评估报告均写本地 `data/`。这意味着 API 与 Worker 必须共享同一持久卷；若迁移到 Cloud Run 的临时文件系统或多副本，当前 FAISS/本地文件设计会失效或产生不一致。
- 前端与 API 同域提供，当前没有 CORS 中间件并不阻塞单域部署；若将前后端拆域，才需要新增严格的允许源配置。
- 当前注册接口公开、登录/注册未见速率限制，JWT 默认有效期 24 小时；公网部署应至少增加入口层限流/Cloud Armor（或代理限流）、决定是否允许公开注册，并评估缩短 token 有效期。
- 上传只校验扩展名和大小，不校验 MIME/内容或恶意文件；面向不受信任用户时，应增加文件内容校验、恶意软件扫描与配额控制。
- FAISS 加载使用 `allow_dangerous_deserialization=True`；只要索引目录完全由可信应用写入且不接受外部索引包即可控制风险，不能让用户或共享不可信主体写该目录。
- README 已给出本地/全 Docker 启动和 Alembic 顺序，但没有 Google Cloud、域名、TLS、Secret Manager、备份恢复、日志轮转、系统更新或灾备说明，因此尚不是完整生产部署手册。
- Google Cloud 当前官方建议：Compute Engine 上的容器可用 Docker/Compose；旧的 VM 创建时 container startup agent 已弃用，应通过 startup script 或 cloud-init 启动容器。镜像应放 Artifact Registry，而不是依赖已停写的 Container Registry。
- Cloud Run 容器文件系统是内存型且实例停止后不持久，因此当前本地上传、报告和 FAISS 索引不能直接迁入 Cloud Run；除非先把文件/报告迁至 Cloud Storage、向量迁至托管/外部 Milvus（或其他数据库），并把 Worker 改造成适合的异步运行形态。
- Google Cloud Secret Manager 官方建议最小权限、按环境隔离，并优先由工作负载身份/实例元数据获取凭据，避免长期服务账号密钥；生产密钥不应继续保存在仓库根目录 `.env`。
- 单 VM 使用 Persistent Disk 保存 `data/` 和自托管数据库卷时，必须配置定期快照及恢复演练；官方建议将关键数据放独立数据盘并使用快照计划。
- 若使用 Cloud SQL，可启用托管备份/时间点恢复并按需要选择 HA；Compute Engine 可通过私网 IP 或 Cloud SQL Auth Proxy 连接。
- HTTPS 可由外部 Application Load Balancer + Google-managed certificate 提供；最低成本单机也可在 VM 上用 Caddy/Nginx 终止 TLS，但仍只对公网放行 80/443。
- 本地验证：`docker compose config --quiet` 成功（exit 0）；Docker 读取用户级 config 时因当前沙箱权限给出警告，但不影响 Compose 文件语法验证。
- Alembic 只有一个当前 head：`20260428_01`。认证、健康检查和文档路径相关定向测试为 13 passed、1 个既有 Starlette 弃用警告。
- Google Cloud VM 运维建议：使用 OS Login/IAM 管理 SSH；可通过 IAP TCP forwarding 让 VM 无需公开 SSH/外部 IP，且应删除对全网开放的默认 SSH 规则。
- Compute Engine 上 Ops Agent 是 Google 当前首选的日志/指标/trace 收集代理；Cloud Armor 可在负载均衡入口对登录、注册、上传等路径做 throttle 或 rate-based ban。
- Linux 容器中的 Celery 仍固定为 `--pool=solo`，会把长耗时入库和评估串行化；生产应根据资源改为 prefork/concurrency，并最好为入库与评估拆队列/Worker，避免评估阻塞上传入库。
- 推荐当前阶段采用单台 Compute Engine：HTTPS 入口 -> API；同一 VM 内运行 API、Worker、Redis，可先保留 PostgreSQL/FAISS；将所有有状态目录放独立 Persistent Disk，并保持单副本。它最贴合现有 Compose 和共享 `data/` 约束。
- 更稳的生产拓扑：外部 Application Load Balancer/托管证书 -> Compute Engine API/Worker，PostgreSQL 攓至 Cloud SQL，Redis 迁至 Memorystore，上传/报告迁至 Cloud Storage，向量使用外部 Milvus/Zilliz 或其他可横向扩展后端；这需要代码适配对象存储，不能只改云配置。
- 上线阻断项：新增 `.dockerignore`；移除内部端口公网映射和弱口令；配置真实 prod 环境变量/密钥；准备域名与 TLS；持久盘和备份；单独执行 Alembic；限制 `/metrics`；建立可探测依赖的 readiness；明确公开注册/限流策略。
- 验收必须覆盖：镜像中无 `.env`/真实数据、仅 80/443 公网可达、迁移到 head、API/Worker/队列正常、上传-索引-问答闭环、VM/容器重启后数据仍在、备份可恢复、日志/告警可见。

## 2026-08-17 生产容器配置第一步
- 用户明确授权的当前范围：修复 `.dockerignore`，新增生产 Dockerfile 和生产 Compose，并确认密码是否可从 `.env` 读取；按步骤慢慢实施。
- 用户指定先运行 grill-me，因此在关键设计选择确认前只做只读分析和规划，不修改 Docker/Compose 业务配置。
- `CLAUDE.md` 被视为参考材料而非独立用户请求；其最小修改、修改前确认方案和验证要求与本轮用户意图一致。
- 用户已确认第一版部署拓扑：单台 Google Compute Engine，同机运行 API、Celery Worker、PostgreSQL、Redis 和 FAISS；本阶段不引入 Cloud SQL、Memorystore、Milvus 或多节点编排。
- 用户已确认第一阶段使用服务器本地 `.env.production` 管理 PostgreSQL、Redis、JWT 和 OpenAI 密钥；真实文件不得提交或进入镜像，并提供无真实值的 `.env.production.example`。
- 用户补充：当前没有域名，但希望部署后完整跑通，并倾向加入 Nginx 与 HTTPS。
- 2026 年当前可行性：Let’s Encrypt IP 地址证书已 GA，Certbot 5.4+ 可申请；证书有效期约 160 小时，必须配置频繁自动续期。Google-managed certificate 仍要求域名/DNS 验证。
- 因 GCE 静态公网 IP 尚未创建，仓库阶段不能预签可信 IP 证书。建议当前配置先纳入 Nginx HTTP 入口并让 API 仅在 Compose 内网暴露；创建 VM/静态 IP 后再启用 Certbot IP 证书和 443。

## 2026-08-10 递归切分实施结果
- `app/rag/splitters.py` 已显式配置递归分隔层级：CRLF/LF 段落与换行、中英文句末标点、分句标点、逗号、空格、空字符串兜底。
- `keep_separator="end"` 使句末标点保留在前一个分块；公开函数签名和 `DocumentChunk` 映射逻辑未改变。
- 新增 4 个切分器单元测试。旧实现基线为 2 failed / 2 passed，失败项正是中英文句界；实现后为 4 passed。
- 相关回归：入库路径 3 passed；检索与 RAG 评估服务 12 passed。
- 全量回归：73 passed、1 skipped、1 warning；skip 为默认关闭的 Milvus 集成测试，warning 为既有 Starlette `python_multipart` 导入弃用提醒。
- 未执行真实索引重建和修改前后质量指标对比：现有评估集指向的 collection/document 与本地 FAISS 索引目录无法只读确认对应关系；重建脚本会先删除旧索引，不能在缺少明确、可恢复的评估文档 ID 时安全执行。

## 2026-08-11 评估页知识库选择优化结果
- `GET /api/v1/collections` 已由后端按当前登录用户的 `owner_id` 隔离，前端可直接复用，无需新增 API。
- 原评估页使用可选文本框手填 `collection_id`；现已改为当前用户知识库下拉框，选项值为 `collection.id`，展示名称和向量后端。
- 运行按钮在未选择知识库、未选择数据集或评估运行中保持禁用；提交载荷始终使用 `state.selectedCollectionId`。
- 加载中、空知识库、加载失败和已选知识库均提供持久 helper 文本；空列表提示用户返回工作台创建知识库并完成索引。
- 浏览器检查确认 375px 视口无水平溢出，评估网格和表单为单列；1280px 为双列；页面控制台无错误。
- 全量测试结果为 74 passed、1 skipped、1 warning。

## 2026-08-11 后台评估、进度查询与排序结果
- 报告列表原先按文件名倒序；现解析每份报告的 `created_at` 为实际时间点后倒序，兼容不同时区偏移。
- `RagEvaluationService.evaluate_retrieval_dataset()` 新增可选进度回调，每完成一个 case 回调 `(completed_cases, total_cases)`，评估算法和报告格式不变。
- 新 Celery 任务 `run_rag_evaluation_task` 在开始时发布 `0/总数`，随后逐 case 更新；成功结果包含报告 ID 和完整 stored report，以兼容未持久化报告。
- `POST /api/v1/evaluations/rag/run` 返回 `202 Accepted`、任务 ID 和总数；`GET /api/v1/evaluations/rag/runs/{task_id}` 返回 queued/running/completed/failed、完成数、总数、错误及最终报告。
- 前端每 1.2 秒轮询一次，显示“已完成 X/总数”和原生进度条；完成后刷新报告列表并打开新报告，失败时给出可感知错误提示。
- Celery 结果后端必须启用；`CELERY_TASK_IGNORE_RESULT=true` 会使进度查询不可用，README 已明确说明。
- 新增任务队列/Worker、API、进度回调、报告排序和页面契约测试；全量结果 82 passed、1 skipped、1 warning。

## 2026-08-11 AI 上下文文档刷新发现
- 用户要求“阅读当前项目最新，更新 AGENT.md 和 AGNET_a_c.md”；仓库中不存在这两个拼写的文件，实际存在并应更新的是 `AGENTS.md` 与 `AGENTS_a_c.md`。
- 当前文件树新增或需纳入上下文的重点包括：`tests/test_splitters.py`、`tests/test_task_queue_service.py`、`data/evals/deepseek_academic_prompts_eval.json`、`data/evals/deepseek_academic_prompts_eval_guide.md`、生产化前端页面结构和后台 RAG 评估任务。
- `app/rag/splitters.py` 已显式配置递归切分分隔符：段落、换行、中英文句末标点、分句标点、逗号、空格和字符兜底，并设置 `keep_separator="end"`。
- `POST /api/v1/evaluations/rag/run` 当前返回 `202 Accepted` 与后台任务 ID；`GET /api/v1/evaluations/rag/runs/{task_id}` 查询 queued/running/completed/failed、完成数、总数、报告和错误。
- `TaskQueueService` 负责投递文档入库与 RAG 评估 Celery 任务，并按 owner_id 隔离评估任务状态查询。
- 评估报告服务按 `created_at` 解析后的时间戳倒序列出报告，并跳过无效报告文件。
- 前端三页已统一为生产化工作台结构，静态资源版本为 `20260811.3`，页面契约测试覆盖产品顶栏、工作台侧栏、知识库选择、评估进度条和 DOM 钩子。
- `.env.example` 已包含 FAISS/Milvus、Celery 结果后端、RAG 检索增强、查询改写和上传限制等配置；文档需强调 `CELERY_TASK_IGNORE_RESULT=false` 对评估进度查询的重要性。
- 本次文档刷新后定向验证 22 passed、1 warning；全量 `python -m pytest -q` 为 82 passed、1 skipped、1 warning。

## 2026-08-11 RAG 评测改进与 LangSmith 规划发现
- 当前 schema 已支持 chunk/document 标签，但 DeepSeek 31 题数据集只填写来源标签；单文档集合的来源命中不能证明召回了正确段落。
- 当前无 chunk 标签时仍构造空 document 主指标，后续第一阶段应先把 source-only 明确表示为“不可测 chunk/document”，避免零分或主指标误导。
- 跨切分策略不能使用顺序型 chunk ID 作为长期真值；应改用文档内容 hash、页码、最小充分证据文本和 quote hash 组成的稳定 evidence 标签。
- 回答完整性应从关键词子串升级为 required facts 的加权覆盖，并与 claim correctness、引用正确性和拒答准确率分开统计。
- 应增加 Gold Evidence 与实际检索两条回答路径，用两者差异区分检索问题和生成问题。
- 当前 Judge 未独立配置时回退回答模型；后续应强制独立 Judge、固定版本、人工校准和 pairwise 随机顺序。
- 当前评估 `total_ms` 包含 retrieval、answer 和 judge；包含 Judge 的均值不能直接解释为用户问答延迟，且真实聊天的查询改写与 TTFT 需要单独 tracing。
- LangSmith 适合承担 tracing、数据集版本、实验比较、pairwise 和人工 annotation queue，但不能自动补出可信 ground truth。
- LangSmith 应采用可选 adapter；关闭或网络失败时本地报告必须继续完成。Cloud 接入前必须确认私有文档原文、问题和答案的数据外发边界。

## 2026-08-12 AI 上下文文档再刷新发现
- 用户再次要求更新 `AGENT.md` 和 `AGNET_a_c.md`；仓库根目录实际仍只有 `AGENTS.md` 与 `AGENTS_a_c.md`，因此更新 canonical 文件，未创建拼写相近的重复文件。
- `docs/` 新增三份前端说明：`CHANGES-2026-08-11.md`、`frontend-fixes-2026-08-11.md`、`nav-view-switching-2026-08-11.md`。
- 首页工作台已从同页锚点滚动升级为 view switching：`data-view` 导航按钮切换 overview / knowledge / documents / chat 四个 `data-view-panel`。
- `app/frontend/static/app.js` 维护 `state.activeView`、`setActiveView()`、hash 同步、`navDocumentsBadge` 和 `refreshDocumentsViewButton`。
- 文档任务视图已有独立 `documentsCollectionSelect`，并与 `collectionSelect` 同步，避免用户回到知识库视图才能切换上下文。
- 概览视图新增 `workspaceActions`、`workspaceRefreshButton`、`recentActivityList`，入口卡片通过 `data-goto-view` 进入具体工作视图。
- 三份前端脚本均应使用 `extractErrorMessage()` 读取后端 `message`、FastAPI 422 `detail[].msg` 和纯文本响应，避免泛化“请求失败”。
- 静态资源版本已从 `20260811.3` 更新到 `20260811.5`。
- `proces.md` 是待实施流程文档，规划 source-only 指标修正、稳定 evidence 标签、required facts、独立 Judge、细粒度延迟 tracing 与 LangSmith 可选 adapter；这些不是已完成业务代码。
- 当前 PATH 中 `python` 优先命中 WindowsApps 启动器并无输出退出；验证改用 `C:\ProgramData\anaconda3\python.exe`。
- 定向测试结果：25 passed、1 warning；全量测试结果：85 passed、1 skipped、1 warning。

## 2026-08-10 指定 PDF 评测资产
- 源文件存在：`C:\Users\林镇州\Desktop\50个顶级的DeepSeek学术论文指令，强烈建议收藏！.pdf`，大小 411750 字节。
- 已定位 bundled Poppler 的 `pdfinfo` 与 `pdftoppm`，可按 PDF 技能要求完成元数据检查和页面渲染。
- PDF 为 38 页 A4，未加密、无表单；已成功渲染全部页面并抽取约 31247 个字符。
- 目视检查第 1-20 页：正文采用编号主题 + 中英文提示词示例结构，主要覆盖学术角色预设、论文写作/摘要/标题、论文续写、大纲、学术润色、语法检查、多版本润色、中英互译和学术翻译。
- 第 3 页含二维码和推广内容，不应作为知识问答评测的主要证据。
- 第 1-7 页可形成事实型评测：角色预设的作用、论文评审专家的输出要求、标题应具备的特征、英文标题输出格式、摘要组成、英文摘要结构、缩写命名、论文续写、致谢和大纲要求。
- 第 8-17 页可形成区分型评测：英文/中文/SCI 润色的输出差异、期刊风格润色、段落逻辑检查、多版本参考、错误反馈、重新回答、纯语法检查、修改定位、专业修改建议、背景原理封装、逻辑论证和个性化润色维度。
- 第 18-20 页可形成翻译型知识问答：学术中英翻译的目标风格、Markdown 三列双版本格式，以及翻译后不重复原文等约束。
- 第 21-25 页覆盖降重策略：调整语序、增减字数、同/近义词替换、主动被动转换、长句拆分、逻辑重组、综合改写、图表呈现和概念解释。
- 第 25-27 页覆盖参考文献与投稿：按模板检查标点/间距、APA 格式、Cover Letter 必备声明、审稿反馈解析和回应计划。
- 第 28-32 页覆盖快速读文献：核心要点九问、通俗总结、1000-1500 字深读、术语表、结构化文献摘要和两篇研究六维比较。
- 第 33-38 页覆盖其他学术场景：期刊匹配、代码解释、独特见解、研究方法评估、可读性、数据源、研究方向搜索、论文总结、研究问题和定性/定量方法建议。
- 数据集应使用 `expected_sources` 精确匹配文件名，而不硬编码当前可能失效的 collection/document ID；运行时通过 `--collection-id` 注入实际集合。
- 已形成 31 个互不重复的评测案例，覆盖写作、润色、翻译、降重、参考文献、投稿、论文阅读及研究设计等主题；每题在 `metadata.evidence_pages` 中记录原文证据页。
- 现有 schema 要求每个案例至少提供一个相关 chunk、文档或来源，因此当前数据集不包含“文档无法回答”的负例；若以后评估拒答能力，应先扩展 schema/runner 对负例的表达与评分。
