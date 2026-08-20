# RAG 评测改进与可观测性实施流程

> 版本：v2（2026-08-17 修订）
> 上一版：v1（2026-08-11）
> 状态：待实施
> 适用项目：ChatRobot_v3
> 文件名按当前约定保留为 `proces.md`。本文只定义实施过程，不代表相关业务代码已经完成。

## 0. 本版修订说明

v1 的方向正确（先修测量、标签不绑 chunk ID、Judge 必须独立、用户延迟与离线开销分离），但对仓库当前状态的诊断有偏差，其中延迟部分会导致优先级排错。本版基于对代码与历史报告的实测核对做以下修订：

| 修订点 | v1 的写法 | v2 的结论 | 依据 |
|---|---|---|---|
| 延迟优化第一步 | Dense/Keyword 并行 | 先修 Milvus keyword 全集合拉取与每查询重连；并行放到最后 | `app/vectorstores/milvus_store.py:299-311`、`:216`、`:292`、`:104` |
| 冻结基线 | 直接冻结现有 31 题报告 | 现有基线 16/31 题因 429 失败，且延迟抖动 3.2 倍，必须重建 | `data/evals/reports/deepseek_recursive_baseline_answer.json` |
| 主指标问题定性 | 「消除误导性指标」 | 主分实际恒为 `0.00`，改进无法被证明，故必须排第一 | `rag_evaluation_service.py:176-185`、`evaluations.js:177` |
| 阶段 2 成本 | 需打通页码 metadata | 页码已全程流通，只缺 `document_key` 与报告项字段 | `splitters.py:62`、`faiss_store.py:49`、`milvus_store.py:201` |
| Judge 校准门槛 | 一致率 ≥80% | 需同时约束分数方差；当前 Judge 在 1.0 处饱和 | 基线 15 题中 11 题打满分 |
| tracing 方案 | 阶段 7 引入 LangSmith | OTel 栈已装好且已接入，先用它；LangSmith 独立决策 | `app/core/tracing.py`、`requirements.txt` |
| langsmith 依赖 | 阶段 7 再声明 | 已通过 langchain 传递安装且未锁版本，当下就要处理 | `pip list`：langsmith 0.7.37 |
| §8.1 用户侧指标 | 评测报告输出 TTFT/user_total | 评测不走 ChatService、不流式，结构性测不出 | `rag_evaluation_service.py:155`、`:607`、`chat_service.py:109-110` |

新增章节：§5.4 指标独立性约束、§8.5 评测链路与用户链路差异、§9.8 依赖治理。

## 1. 目标

在当前递归切分、混合检索、重排、异步评估和前端评估看板基础上，依次解决：

1. DeepSeek PDF 数据集只有来源级标签，不能衡量 chunk/document 检索质量，且主指标恒为 0。
2. 回答完整性主要依赖关键词子串和词项相似度，不能判断必需事实是否全部回答。
3. LLM Judge 未独立配置时使用回答模型，自评独立性不足且分数饱和。
4. 现有延迟数字不可信（基线残缺、抖动大），且未区分用户问答、离线 Judge 和检索内部阶段。
5. 缺少跨实验对比、人工标注队列和完整调用链追踪。

最终形成两层能力：

- 本地评估：稳定、可离线运行、可在现有前端操作的主链路。
- 可观测性层：先用已有 OTel 提供阶段级 span；LangSmith 作为可选的实验比较与人工反馈层，不替代本地真值和报告。

## 2. 当前基线与已核实缺陷

### 2.1 已具备

- 中英文友好的递归切分（`app/rag/splitters.py`）。
- Dense + Keyword 混合检索、RRF 融合和启发式重排。
- `RagEvaluationDataset`、检索指标、回答指标、LLM Judge、耗时和 token 指标。
- Celery 后台评估、逐 case 进度、历史报告和前端评估看板。
- 31 个基于指定 PDF 的问答案例，含参考答案、关键词、来源文件名和证据页码。
- 完整 OTel 栈（api/sdk/otlp-http + fastapi/celery/sqlalchemy instrumentation）已在 `requirements.txt` 声明并安装，`app/core/tracing.py` 已接入 FastAPI、SQLAlchemy、Celery，默认由 `observability_tracing_enabled=false` 关闭。
- Prometheus HTTP 与 Celery 延迟 histogram 已就绪（`app/core/metrics.py`）。

### 2.2 已核实缺陷（按影响排序）

**D1 主指标恒为 0，改进不可证明。**
`rag_evaluation_service.py:176-185`：无 chunk 标签时把 `primary_label_level` 置为 `"document"`，再回落到全零 bundle，而不是「不可测」。前端把它作为头号指标：`evaluations.js:177`（最新主分）、`:310` Recall@K、`:311` MRR@K、`:256`、`:331`。三份历史报告 `primary_metrics` 全部为 0.0，而 `source_metrics.source_match` 为 1.0。**在修复前，任何检索改动都是 0 到 0。**

**D2 Milvus keyword 检索无上限，且每次检索重做握手。**
`milvus_store.py:299-311`：`collection.query(expr=collection_id == X, output_fields=[..., "text", ...])` 无 `limit`，把整个集合连全文拉回本地再用 Python 打分，O(N) 网络传输，随语料线性恶化。叠加每次检索的 `_connect()`（:216、:292）、`has_collection()`、以及 `_ensure_collection()` 内的 `collection.load()`（:104）。一次 hybrid 查询约为：2 次 connect + 3 次 has_collection + 1 次 collection.load + 1 次全集合扫描 + 1 次 embed。

**D3 FAISS 每次检索重新读盘。**
`faiss_store.py:23-33` `_load_store()` 每次检索都 `FAISS.load_local()` 读盘并反序列化 docstore，hybrid 模式一次查询读两遍，无任何缓存。这对生产要紧：`task_plan.md` 阶段 14 的目标是单机 FAISS。

**D4 冻结基线不可信。**
`deepseek_recursive_baseline_answer.json`：31 题中 16 题因 HTTP 429 失败，仅 15 题有答案与 Judge 分；报告并列展示 primary `case_count: 31` 与 answer `case_count: 15`。同代码延迟抖动：retrieval P95 在 2601 / 5926 / 8267 ms 之间（3.2 倍），total avg 在 1980 / 3853 / 17363 ms 之间。

**D5 Judge 即回答模型，且分数饱和。**
`.env` 中 `OPENAI_MODEL=deepseek-v4-flash-0731`，`RAG_EVAL_LLM_JUDGE_MODEL` 未设置 → `rag_evaluation_service.py:710` 回落到回答模型。实测：Judge overall 0.897–0.917、groundedness 0.976–0.987，而确定性 groundedness 仅 0.53；基线 15 题中 11 题 Judge 打满分 1.0。

**D6 报告项丢弃证据匹配所需字段。**
`rag_eval.py:50-57` `RagRetrievedItem` 只有 rank/document_id/chunk_id/source_name/source_path/score/retrieval_channels，**没有 `page` 和 `content`**。而 chunk metadata 在评测时是可得的，构造报告时被丢掉。

**D7 指标循环论证。**
`compute_keyword_score`（`retrieval.py:47`）同时用于关键词检索（`faiss_store.py:134`、`milvus_store.py:315`）、重排（`rerank_chunk_score`）和 groundedness 评分（`rag_evaluation_service.py:865`）。因共享词项被召回的 chunk，必然「支持」共享同样词项的答案。groundedness 阈值 `0.35`（`:873`、`:877`）是作用在 bigram 词袋分上的魔数，无依据。

**D8 评测链路 ≠ 用户链路。**
评测直接调 `retrieval_service.retrieve`（`:155`）与一次性 `llm.invoke`（`:607`），不经过 `ChatService`、不流式、不传 history，因此 `chat_service.py:109-110` 的查询改写直接早退。`query_rewrite_ms` 结构性恒为 0，TTFT 不可观测。

**D9 句子切分把 markdown 标记当句子。**
`_SENTENCE_SPLIT_PATTERN`（`:46`）导致 `unsupported_statements: ["**"]`，拉低 `grounded_sentence_ratio`。量级有限（一份报告 17 条中 2 条，另一份 29 条中 0 条），属搭车修复。

**D10 Milvus expr 字符串插值。**
`_escape`（`:65-66`）只转义 `\` 与 `"`，expr 由插值构造（:223、:298）。`collection_id` 为服务端 UUID，当前风险低，属搭车加固。

**D11 后端与生产目标不一致。**
`.env` 为 `VECTOR_BACKEND=milvus`，`task_plan.md` 阶段 14 生产目标为单机 FAISS。证据匹配语义必须一致，但**延迟数字在两后端间不可迁移**。

**D12 langsmith 已被传递安装。**
`langsmith 0.7.37` 经 langchain 进入环境，`requirements.txt` 未声明、未锁版本。

### 2.3 仍然成立的原有限制

- 31 个案例的 `relevant_chunk_ids` 和 `relevant_document_ids` 为空。
- 单文档集合中 source hit 容易饱和（实测 1.0），不代表召回了正确段落。
- `chunk_id={document_id}-{index}`（`splitters.py:57`）随重新切分变化，不适合作为跨切分策略的长期真值。
- `expected_answer_contains` 只能做字面命中检查。

### 2.4 已核实为「非问题」

- **报告中文乱码**：`data/evals/reports/*.json` 中 `source_name`、Judge `rationale` 在部分终端显示为乱码，但按 codepoint 校验（`0x4e2a`=个、`0x9876`=顶、`0x7ea7`=级）为**正确 UTF-8**，写入路径 `rag_evaluation_report_service.py:151-154` 使用 `ensure_ascii=False` + `encoding="utf-8"`。属终端渲染问题，不需修复。
- **PDF 页码链路**：`PyPDFLoader` 产出的 `page` 经 `splitters.py:62` 透传，落入 FAISS（`faiss_store.py:49` `**chunk.metadata`）与 Milvus（`milvus_store.py:201` `metadata_json`）。链路已通，阶段 2 成本低于 v1 预估。

## 3. 实施原则

1. 先修正测量，再修改检索或生成算法。
2. **性能修复按「是否改变召回语义」拆分**：不改变语义的（连接复用、句柄缓存、计时）可以早做，只需 no-diff 校验；改变语义的（keyword 加上限、上下文裁剪）必须等可信测量就位。
3. 每次实验只改变一个主要变量。
4. 标准标签必须独立于 chunk ID 和数据库自增 ID。
5. 确定性规则优先，LLM Judge 只评价难以用规则表达的语义质量。
6. **新指标不得复用 `compute_keyword_score`**（见 §5.4）。
7. 用户延迟与离线评估开销分开统计；测不出的指标标注为不可测，不得填 0。
8. 可观测性优先使用仓库已有的 OTel；引入第三方平台必须可选，关闭或不可用时本地功能不受影响。
9. 未经确认不得向第三方平台发送私有文档原文。
10. 每个阶段先写失败测试，再做最小实现，再运行相关与全量回归。

## 4. 目标数据模型

### 4.1 稳定文档标识

为入库文档计算稳定键：

```text
document_key = sha256(原始文件字节)
```

评测标签使用 `document_key`，不直接依赖重新上传后可能变化的数据库 `document_id`。这是阶段 2 唯一确实缺失的链路（页码已通，见 §2.4）。

### 4.2 证据级标签

在 `RagEvaluationCase` 中新增结构化证据标签：

```json
{
  "relevant_evidence": [
    {
      "evidence_id": "abstract-components",
      "document_key": "sha256:...",
      "source_name": "50个顶级的DeepSeek学术论文指令，强烈建议收藏！.pdf",
      "page_start": 5,
      "page_end": 5,
      "section": "摘要组成",
      "text": "人工选取的最小充分证据",
      "text_sha256": "sha256:...",
      "relevance_grade": 2
    }
  ]
}
```

`relevance_grade`：

- `0`：与问题无关。
- `1`：部分相关，单独不足以回答。
- `2`：包含直接、充分的回答证据。

评估时通过文档键、页码、文本覆盖率和规范化 quote hash 将新 chunk 映射到稳定证据，不要求 chunk ID 永久不变。

**注意页码基准**：`PyPDFLoader` 的 `page` 为 0-based，而人工标注的 `evidence_pages`（现有 31 题 metadata 中已有）为 1-based。映射实现必须显式转换，并用测试锁定该约定。

### 4.3 报告项字段补全（新增，阶段 1 前置）

`RagRetrievedItem` 需增加：

```text
page: int | None          # 来自 chunk metadata["page"]，0-based 原值
content: str | None       # 用于证据覆盖率与人工复核
metadata: dict            # 保留 document_key 等后续字段
```

不补这三项，阶段 2 的证据匹配无法从报告侧验证，人工复核也无从下手。

### 4.4 原子事实标签

```json
{
  "answerable": true,
  "required_facts": [
    {
      "fact_id": "abstract-purpose",
      "description": "摘要应包含研究目的",
      "weight": 1.0,
      "evidence_ids": ["abstract-components"]
    }
  ],
  "optional_facts": [],
  "forbidden_claims": [],
  "expected_format": null
}
```

旧字段保留一个兼容周期：

- `expected_sources` 继续作为来源级冒烟指标。
- `expected_answer_contains` 继续作为确定性辅助指标。
- 新报告优先展示 evidence/fact 指标。

## 5. 目标指标体系

### 5.1 检索指标

必须新增：

- `evidence_recall_at_k`：Top-K 覆盖的标准证据比例。
- `evidence_precision_at_k`：Top-K 中与标准证据相关的结果比例。
- `evidence_mrr_at_k`：首个充分证据的位置。
- `evidence_ndcg_at_k`：使用 0/1/2 分级相关性计算排序质量。
- `fact_coverage_at_k`：Top-K 上下文覆盖的必需事实比例。
- `retrieval_sufficiency`：Top-K 的证据合集是否足以回答完整问题。

指标展示规则（对应 D1）：

- 有 evidence 标签：以 evidence 指标作为主指标。
- 只有 document 标签：以 document 指标作为主指标。
- 只有 source 标签：显示 `source-only`，不生成误导性的 chunk/document 主指标。
- 没有对应标签：显示「不可测」。**禁止用 `0` 代替「没有标签」**——这正是 D1 的成因。

### 5.2 回答指标

新增：

- `fact_completeness`：必需事实的加权召回率。
- `claim_correctness`：答案陈述中被标准证据支持的比例。
- `citation_precision` / `citation_recall`：引用是否支持对应陈述、关键事实是否给出引用。
- `format_compliance`：列表、表格、步骤等格式约束是否满足。
- `abstention_accuracy`：无答案案例是否正确拒答。
- `answer_quality_f1`：完整性与正确性的调和平均。

保留但降低权重：`expected_term_recall`、`query_term_coverage`、`reference_similarity`。

### 5.3 两条回答评测路径

```text
标准证据 → 回答模型 → 测量生成器能力
实际召回 → 回答模型 → 测量完整 RAG 能力
```

差值用于定位：

- 标准证据回答完整、实际召回不完整：优先修检索。
- 两者都不完整：优先修回答 prompt、上下文组织或回答模型。
- 实际召回已覆盖事实但答案遗漏：检查长上下文位置和生成约束。

### 5.4 指标独立性约束（新增，对应 D7）

`compute_keyword_score` 当前同时驱动召回、重排和 groundedness 评分。因共享词项而被召回的 chunk，必然「支持」共享同样词项的答案，因此现有 groundedness 部分测量的是词项重合而非事实支持。

新增指标必须遵守：

1. **`fact_completeness`、`claim_correctness` 不得复用 `compute_keyword_score`。** 事实判定使用独立机制：证据文本的规范化子串/quote hash 匹配，或独立 Judge，二者都不共享检索打分函数。
2. **groundedness 阈值 `0.35` 必须改为具名配置项**并记录其标定方式；在没有标定依据前不得作为验收门槛。
3. 报告中同时保留「基于词项的 groundedness」和「基于证据的 claim_correctness」，二者差值本身是检索-生成耦合度的诊断信号。
4. 任何以关键词分为输入的新指标，必须在测试中包含一个「词项高度重合但事实错误」的反例，证明该指标能区分。

## 6. 标注流程

### 6.1 第一批范围

先升级现有 31 个案例：

1. 为每题选择最小充分证据。
2. 拆分 `required_facts`。
3. 记录证据页、章节、原文和 hash（注意 §4.2 的 0-based/1-based 转换）。
4. 给证据设置 1/2 级相关性。
5. 验证重新切分后仍能映射到证据。

### 6.2 增强数据集

第一批标签稳定后再增加：

- 至少 10 个跨文档 hard-negative 案例。
- 至少 5 个文档无法回答的拒答案例。
- 多跳问题、跨页问题和多事实问题。
- 短事实问题与长结构化回答问题。
- 真实用户低评分问题，经脱敏后进入回归集。

### 6.3 人工标注质量

- 至少 20% 的案例由两人独立标注，标注者彼此不可见。
- 分歧案例统一仲裁并记录原因。
- 数据集修改后生成新版本，旧实验继续绑定旧版本。

## 7. 独立 Judge 方案

### 7.1 模型隔离

- 回答模型与 Judge 使用不同模型系列，条件允许时使用不同供应商。当前 `.env` 的 `OPENAI_MODEL=deepseek-v4-flash-0731` 与未设置的 `RAG_EVAL_LLM_JUDGE_MODEL` 构成 D5。
- 强制配置 `RAG_EVAL_LLM_JUDGE_MODEL`；未配置时 Judge 模式**不得静默回退到回答模型**（移除 `rag_evaluation_service.py:710` 的回退）。
- `auto` 模式在 Judge 不可用时记录明确状态；`require` 模式直接失败。
- 报告保存回答模型、Judge 模型、prompt 版本和运行时间。

### 7.2 评分组合

```text
确定性代码评分 + 独立 LLM Judge + 人工抽检/仲裁
```

Judge 分别评价：事实完整性、证据一致性、问题相关性、引用正确性、无依据扩写。

### 7.3 校准（对应 D5 的饱和问题）

v1 的「等级一致率 ≥80%」在当前条件下几乎零成本达标：Judge 在 1.0 处饱和（基线 15 题中 11 题满分），一个恒输出 1.0 的 Judge 也能在多数为好答案的数据集上取得高一致率。因此必须同时约束区分度：

- 建立一批人工金标准答案和人工分数。
- 等级一致率不低于 80%。
- 排序相关性（Spearman）不低于 0.7。
- **新增：分数分布约束。** 单一分值占比不得超过 40%，且分数标准差不得低于 0.1。达不到即视为 Judge 无区分度，不得用于门禁。
- **新增：植入式验证。** 校准集必须包含至少 5 个人工构造的劣质答案（事实错误、遗漏必需事实、无依据扩写各类），Judge 必须能把它们排在真实答案之下，否则校准不通过。
- Judge 模型或 prompt 改变后必须重新校准。
- A/B Judge 随机交换两个答案顺序，减少位置偏差。

## 8. 延迟测量与优化

### 8.1 先修正统计口径

分别定义：

- `user_total_ms`：真实用户从提交问题到回答完成。
- `time_to_first_token_ms`：流式首字时间。
- `evaluation_total_ms`：离线评估总耗时。
- `judge_ms`：离线 Judge 耗时，不计入用户问答延迟。

不得继续把包含 Judge 的 `avg_total_ms` 直接表述为产品问答耗时。**其中 `user_total_ms` 与 `time_to_first_token_ms` 当前评测链路测不出，见 §8.5。**

### 8.2 检索内部阶段

新增计时：`query_rewrite_ms`、`query_embedding_ms`、`dense_search_ms`、`keyword_search_ms`、`fusion_ms`、`rerank_ms`、`context_build_ms`、`answer_ttft_ms`、`answer_generation_ms`。

所有阶段同时汇总平均值、P50、P95 和最大值。**实现方式优先使用已有 OTel span（见 §9.1）+ 进程内计时写入报告，不需要引入新供应商。**

### 8.3 优化顺序（本版重排，对应 D2/D3）

v1 把「Dense/Keyword 并行」列为第 1 步。按实测，Milvus 后端的 keyword 检索会拉取整个集合（D2），并行化只能省下较小的一半，同时把 Milvus 并发压力翻倍。正确顺序：

**A 组：不改变召回语义，可立即执行，只需 no-diff 校验**

1. 复用 Milvus 连接与 collection 句柄，`collection.load()` 只在启动/首次访问时执行一次，不在每次检索时重做（`milvus_store.py:216`、`:292`、`:104`）。
2. 缓存 FAISS store 句柄，按 `collection_id` + index 文件 mtime 失效，消除每次检索的读盘与反序列化，并消除 hybrid 模式下的双次加载（`faiss_store.py:23-33`）。
3. 加入 §8.2 的阶段计时，先测再改后续任何一项。

**B 组：改变召回语义，必须在 D1、D4 修复之后**

4. 给 keyword 检索加上限：改用 Milvus 原生全文/BM25 检索，或至少加 `limit` 与服务端过滤，避免全集合传输（`milvus_store.py:299-311`）。
5. 先宽召回，再裁剪进入回答上下文的 chunk；避免无条件使用最大 8000 字符上下文。
   **约束：裁剪依据只能是线上可得的信号（分数、去重、位置），严禁使用 evidence/gold 标签，否则等于把真值泄漏进产品路径。**
6. 仅在问题存在上下文依赖时调用查询改写；查询改写使用更快模型，并限制历史消息和输出长度。

**C 组：收益依赖具体场景，最后评估**

7. 为重复问题缓存 query embedding；缓存键必须包含 embedding 模型版本。
   **注意：该项在评测集上收益为零（31 题各不相同且各跑一次），不得计入 §8.4 的评测侧目标，只在生产重复提问场景计量。**
8. 将 Dense 与 Keyword 检索并行执行——**仅在 A 组与 B 组第 4 项完成后重新测量，若届时仍是瓶颈才做**。
9. 使用流式输出改善 TTFT（`chat_service.py:252` 已实现流式，需要的是把 TTFT 纳入测量）。
10. Judge 只在后台评估任务执行，不阻塞用户问答。
11. 批量评估允许有限并发，但分别记录单请求延迟和整批墙钟时间。

### 8.4 验收目标（本版重写，对应 D4）

v1 要求「P95 下降至少 20%」，但同代码实测 retrieval P95 在 2601 / 5926 / 8267 ms 之间波动 3.2 倍，20% 远小于噪声，结论不可证伪。改为：

- 基线必须为 **31/31 题全部成功**的运行（429 需重试至完成），且**同配置重复 N≥3 次**。
- 门槛按实测标准差设定：改进量必须大于 `2σ`，其中 σ 取基线 3 次运行的 P95 标准差。若 `2σ > 20%`，则以 `2σ` 为门槛并在报告中记录该数值。
- 报告必须记录后端类型（Milvus/FAISS）；**跨后端的延迟数字不得直接比较**（D11）。
- evidence recall、fact completeness 和 groundedness 不得下降超过 0.02。
- Judge 耗时不进入用户延迟指标。
- 质量越过退化线时不得合并该优化。

### 8.5 评测链路与用户链路差异（新增，对应 D8）

当前评测直接调 `retrieval_service.retrieve`（`rag_evaluation_service.py:155`）与一次性 `llm.invoke`（`:607`），**不经过 `ChatService`、不流式、不传 history**。因此 `chat_service.py:109-110` 的查询改写直接早退，`query_rewrite_ms` 结构性恒为 0，TTFT 完全不可观测。

必须在两条路线中选一条，并在报告中明确标注：

- **路线 A（推荐）**：让评测经由 `ChatService` 的流式路径运行，从而 `user_total_ms`、`time_to_first_token_ms`、`query_rewrite_ms` 真实可测。代价是评测需要 conversation 上下文，且需为「带历史」的多轮案例扩展数据集。
- **路线 B**：评测继续走当前直连路径，`user_total_ms` 与 TTFT **标注为不可测**，改由线上 Prometheus histogram（`app/core/metrics.py` 已就绪）采集，报告中只呈现 retrieval/answer/judge 三段。

无论选哪条，都不得在评测报告里输出一个恒为 0 的 `query_rewrite_ms` 并当作「改写很快」的证据——那是 D1 的同类错误。

## 9. 可观测性方案

### 9.1 先用已有 OTel，不要为 tracing 引入新供应商

v1 把 tracing 需求整体压在阶段 7 的 LangSmith 上。实际情况：

- `requirements.txt` 已声明 `opentelemetry-api/sdk/exporter-otlp-proto-http` 与 fastapi/celery/sqlalchemy instrumentation，且均已安装（1.41.1 / 0.62b1）。
- `app/core/tracing.py` 已实现 provider 初始化与三处 instrumentation，仅由 `observability_tracing_enabled=false` 关闭。

§9.4 想要的那棵 span 树用 OTel 今天就能实现：不引入新供应商、不触发 §9.7 的隐私审批、直接回答「11 秒花在哪」。因此：

- **阶段 6 的延迟诊断用 OTel custom span + 进程内计时完成。**
- **LangSmith 降级为独立的、更晚的、按需决策**，其论证依据必须是它独有的能力（数据集版本管理、pairwise 比较 UI、annotation queue、线上反馈回流），**不能是 tracing**——tracing 已经具备。

### 9.2 LangSmith 定位（若届时决定采用）

LangSmith 用于：数据集版本和实验记录、多实验并排比较、自定义 code/LLM evaluator、Pairwise 对比和人工 annotation queue、线上抽样与反馈回流。

LangSmith 不负责：自动生成可信 evidence 真值、替代本地评估报告、替代当前前端评估看板、绕过知识库数据隐私审批。

### 9.3 配置

```text
LANGSMITH_ENABLED=false
LANGSMITH_API_KEY=
LANGSMITH_ENDPOINT=
LANGSMITH_PROJECT=chatrobot-rag
LANGSMITH_TRACING_SAMPLING_RATE=1.0
LANGSMITH_HIDE_INPUTS=false
LANGSMITH_HIDE_OUTPUTS=false
```

要求：`.env.example` 只放空值或安全默认值；API key 不写入代码、数据集和报告；`LANGSMITH_ENABLED=false` 时不得发起任何 LangSmith 网络请求。

### 9.4 Trace 层级（OTel span 命名同此结构）

```text
rag_request
├── query_rewrite
├── retrieval
│   ├── query_embedding
│   ├── dense_search
│   ├── keyword_search
│   ├── rrf_fusion
│   └── rerank
├── context_build
├── answer_generation
└── offline_judge
```

每次运行附加 metadata：splitter 名称和版本、chunk size/overlap、embedding 模型、vector backend、Top-K/hybrid/rerank、回答模型、Judge 模型、数据集版本、prompt 版本、应用 revision/build ID。

### 9.5 数据集映射（LangSmith 采用时）

```text
inputs:            query / collection_id 或语料版本 / retrieval_config
reference_outputs: reference_answer / relevant_evidence / required_facts / answerable
outputs:           answer / retrieved_items / matched_evidence_ids / latency_metrics / token_usage
```

同步必须幂等：本地 `case_id + dataset_version` 映射到稳定的 LangSmith example key，重复同步只更新对应版本。

### 9.6 前端结合方式

保留现有 `/evaluations` 工作流，逐步增加：实验名称输入框、配置快照展示、可选同步开关、实验链接、本地两报告并排比较、质量与延迟回归高亮。

**优先修复项**：`evaluations.js:177`、`:256`、`:310`、`:311`、`:331` 目前把 `primary_metrics.recall_at_k` 作为头号指标显示，在 source-only 数据集上恒为 `0.00`。必须改为按 `primary_label_level` 渲染，「不可测」显示为占位符而非数字。

前端触发后仍由现有 Celery 任务运行，不在浏览器中直接调用外部 API，也不暴露任何 API key。

### 9.7 隐私边界

接入任何云端 tracing 前必须确认：是否允许上传用户问题、答案和召回原文；是否只记录 metadata、hash 和截断文本；是否需要 PII 脱敏；哪些用户/集合必须完全关闭 tracing；trace 保留期限和删除流程。

如果隐私要求不允许外发原文，则保留本地评估 + 本地 OTel collector；不要为了 tracing 破坏数据边界。**自建 OTel collector 不出网，是隐私敏感场景的默认选项。**

### 9.8 依赖治理（新增，对应 D12）

`langsmith 0.7.37` 已经通过 langchain 传递安装进入环境，而 `requirements.txt` 未声明、未锁版本。这意味着：

- 一次 langchain 升级就可能改变 langsmith 行为，且没有任何显式记录。
- v1 §9.3 那句「SDK 作为直接依赖明确声明，不依赖 LangChain 的传递安装」判断正确，但**这是当下就该处理的动作，不是阶段 7 的议题**。

立即处理（放入阶段 1）：

1. 若确定后续会用：在 `requirements.txt` 显式声明并锁定 `langsmith==<已验证版本>`。
2. 若确定不用或未决：显式记录当前传递版本，并在 CI 中加入依赖快照检查，避免静默漂移。
3. 无论哪种，确认 `LANGCHAIN_TRACING_V2` / `LANGSMITH_TRACING` 等环境变量在本地与生产均未被意外置为真——否则 langchain 会在无人察觉的情况下尝试外发 trace。

## 10. 分阶段实施（本版重排）

排序理由：v1 把性能修复整块压在阶段 6。本版按 §3 原则 2 把「不改变召回语义」的性能修复提前到阶段 1B——它们不影响任何指标语义，却能显著缩短后续每一轮评测的等待时间（当前一轮 31 题约 9 分钟，后续阶段要反复跑，收益复利）。改变召回语义的部分仍然留在可信测量之后。

### 阶段 1A：测量诚实化（最高优先，纯测量层）

候选文件：`app/schemas/rag_eval.py`、`app/services/rag_evaluation_service.py`、`app/frontend/static/evaluations.js`、`tests/test_rag_evaluation_service.py`、`tests/test_web_page.py`

实施：

- 允许主检索指标为「不可测」，移除 `rag_evaluation_service.py:176-185` 的全零回落（D1）。
- source-only 数据集不再生成伪 document 主分数；面板明确标记「仅能测来源命中」。
- `RagRetrievedItem` 增加 `page`、`content`、`metadata` 三字段（D6，§4.3）。
- 评测执行加入 429 重试与退避，确保 31/31 完成（D4 前置）。
- `requirements.txt` 处理 langsmith 传递依赖（D12，§9.8）。

验收：

- source-only 报告不再显示误导性的 Precision/MRR/nDCG，前端主分位显示占位符而非 `0.00`。
- 旧报告仍可读取，或提供明确兼容转换。
- 一次完整运行产出 31/31 有答案的报告。

### 阶段 1B：语义不变的性能修复 + 阶段计时

候选文件：`app/vectorstores/milvus_store.py`、`app/vectorstores/faiss_store.py`、`app/services/retrieval_service.py`、`app/core/tracing.py`

实施：

- Milvus 连接与 collection 句柄复用，`load()` 不在每次检索时重做（D2 的握手部分）。
- FAISS store 句柄缓存，按 index mtime 失效（D3）。
- 加入 §8.2 阶段计时与 §9.4 OTel span。

验收：

- **no-diff 校验**：同一数据集、同一 seed 下，改动前后的召回结果集与排序完全一致（这是「语义不变」的定义，必须有测试）。
- 阶段计时字段完整、非负，且各阶段之和与总耗时的差值在可解释范围内。
- 单轮 31 题墙钟时间下降，且下降来自握手/读盘而非召回变化。

### 阶段 2：可信基线冻结

实施：

- 在阶段 1A/1B 完成后，以 31/31 成功的运行**重复 N≥3 次**建立基线。
- 记录模型、索引、切分、Top-K、后端类型和环境配置。
- 计算并记录各延迟指标的标准差，据此确定 §8.4 的门槛。
- 将 retrieval、answer、judge 耗时分开解释。

验收：

- 基线可以从前端重复运行。
- 三次重复运行的确定性检索指标完全一致。
- 报告能追溯到完整配置，并显式记录后端类型与 σ 值。

### 阶段 3：证据标签和稳定映射

候选文件：`app/schemas/rag_eval.py`、`app/services/ingestion_service.py`、`app/services/rag_evaluation_service.py`、`data/evals/deepseek_academic_prompts_eval.json`

实施：

- 新增 evidence schema（§4.2）。
- 计算并保存 `document_key`（§4.1，这是唯一确实缺失的链路）。
- 实现 evidence overlap 和分级相关性评分，读取已有的 `metadata["page"]`（§2.4）。
- 为 31 题补全最小充分证据，注意 0-based/1-based 转换。

验收：

- 同一 evidence 数据集能评价至少两种不同切分结果。
- 重切分后无需人工更新 chunk ID。
- FAISS 与 Milvus 的 evidence 匹配语义一致（延迟数字不要求可比，见 D11）。
- 页码基准转换有专门测试锁定。

### 阶段 4：改变召回语义的性能修复

候选文件：`app/vectorstores/milvus_store.py`、`app/services/retrieval_service.py`

实施：

- keyword 检索加上限或改用 Milvus 原生全文/BM25（§8.3 B 组第 4 项，D2 的主体）。
- 上下文裁剪（§8.3 B 组第 5 项，注意禁止使用 gold 标签）。
- 查询改写按需执行。
- 搭车加固 Milvus expr 转义（D10）。

验收：

- 相对阶段 2 基线，延迟改进量大于 `2σ`。
- evidence recall / fact completeness / groundedness 下降不超过 0.02。
- keyword 检索的网络传输量不再随集合规模线性增长（需有量化证据）。

### 阶段 5：独立 Judge 与人工校准

候选文件：`app/core/config.py`、`.env.example`、`app/services/rag_evaluation_service.py`

实施：

- 移除 `rag_evaluation_service.py:710` 的静默回退（D5）。
- 固定结构化评分 rubric。
- 建立人工校准集（含 §7.3 要求的 5 个植入劣质答案）和 pairwise 评估。

验收：

- 报告可以证明回答模型与 Judge 模型不同。
- 一致率 ≥80%、Spearman ≥0.7、**单一分值占比 ≤40%、标准差 ≥0.1**。
- Judge 能把植入的劣质答案排在真实答案之下。

### 阶段 6：多文档、hard negative 和拒答集

实施：建立独立评测集合并加入主题相近的干扰文档；增加无答案、多跳、跨页和多事实案例；补充 `answerable` 与拒答评分。

验收：source hit 不再因单文档集合天然饱和（当前实测 1.0）；可以计算错误来源率和拒答准确率。

### 阶段 7：回答完整性

候选文件：`app/schemas/rag_eval.py`、`app/services/rag_evaluation_service.py`、`app/rag/prompts.py`、`app/frontend/static/evaluations.js`

实施：

- 新增 required facts、forbidden claims 和 expected format。
- 实现事实级完整性与正确性评分，**遵守 §5.4 的独立性约束**。
- 增加 Gold Evidence 回答模式（§5.3）。
- 把 groundedness 阈值 `0.35` 提为具名配置并记录标定方式（D7）。
- 搭车修复 markdown 标记被当作句子的问题（D9）。
- 面板显示遗漏事实和不受支持陈述。

验收：

- 能明确区分「检索遗漏」和「模型看到证据仍未回答」。
- 事实完整性评分可追溯到具体 `fact_id`。
- 存在「词项高度重合但事实错误」的测试反例，且新指标能区分（§5.4 第 4 条）。

### 阶段 8：LangSmith 决策与 POC（可选）

**前置条件：阶段 1B 的 OTel span 已经满足延迟诊断需求。** 只有在明确需要数据集版本管理、pairwise UI 或 annotation queue 时才进入本阶段。

实施：显式声明并锁定 SDK 与配置；先对非敏感评测集合启用；同步 31 题数据集和自定义 evaluator；运行 baseline/候选实验并使用 Compare；试用 annotation queue 校准失败案例。

验收：能看到完整 RAG 子步骤和实验配置；本地报告与外部平台的确定性指标一致；关闭或网络失败时本地评估仍成功；没有未经授权的私有原文被上传。

### 阶段 9：产品化与回归门禁

实施：本地看板加入实验标签、报告对比和回归高亮；关键确定性指标加入 pytest/CI 门禁；低分线上 trace 经人工审核后回流离线数据集。

验收：每次切分、检索、模型或 prompt 变更都有可比较实验；质量或延迟越过门槛时自动阻止发布。

## 11. 建议测试清单

### Schema

- evidence/fact 新字段校验。
- 旧 JSON 兼容读取。
- 无答案案例允许没有 relevant evidence。
- evidence ID 和 fact ID 唯一性。
- `RagRetrievedItem` 的 `page`/`content`/`metadata` 正确从 chunk metadata 透传。

### 检索评分

- 同一证据被不同 chunk 边界覆盖时得到相同 relevance 结论。
- 部分覆盖和充分覆盖得到不同 relevance grade。
- **source-only 数据集产出「不可测」而非 0**（D1 回归测试）。
- 多文档 hard negative 会降低错误召回分数。
- 页码 0-based/1-based 转换正确（§4.2）。

### 性能修复（新增）

- **no-diff 测试**：Milvus 句柄复用、FAISS 句柄缓存前后，召回结果集与排序完全一致。
- FAISS index 文件变更后缓存正确失效。
- keyword 检索的查询带有 limit，不做全集合拉取（可用 mock 断言传入参数）。
- 阶段计时字段非负、完整，各阶段之和不超过总耗时。

### 回答评分

- 同义改写仍能命中原子事实。
- 只提关键词但未表达完整事实不能得满分。
- **「词项高度重合但事实错误」的答案被 claim_correctness 判为低分**（§5.4）。
- 错误陈述进入 forbidden/unsupported 结果。
- 无答案问题正确拒答。
- Gold Evidence 与实际检索模式正确隔离。
- markdown 标记不被计为句子（D9）。

### Judge

- **未配置独立模型时抛错或明确跳过，不静默自评**（D5）。
- Judge 失败不丢失确定性指标。
- Pairwise 输出顺序随机化。
- 模型和 prompt 版本写入报告。
- 植入的劣质答案被排在真实答案之下（§7.3）。

### 延迟

- 各子阶段计时非负且字段完整。
- Judge 不计入 `user_total_ms`。
- 并行检索结果与串行基线语义一致（若最终执行 §8.3 C 组第 8 项）。
- 流式请求记录 TTFT，或明确标注为不可测（§8.5）。
- 429 重试逻辑在注入失败时仍能完成 31/31。

### 可观测性

- OTel 关闭时零 span 导出。
- OTel span 层级与 §9.4 一致（可用 in-memory span exporter 断言）。
- LangSmith disabled 模式零网络调用。
- 数据集同步幂等。
- 外部平台故障不影响本地报告。
- 脱敏函数不会泄露已定义的敏感字段。

## 12. 风险与回退

| 风险 | 处理方式 |
|---|---|
| 重切分导致 chunk ID 变化 | 使用稳定 evidence span，不以 chunk ID 作为长期真值 |
| 文档解析变化导致证据文本变化 | 同时保存 document hash、页码、规范化文本和 quote hash；运行前校验 |
| 页码基准混用（0-based vs 1-based） | 显式转换 + 专门测试锁定约定 |
| 标注成本过高 | 先完成现有 31 题，再通过失败案例逐步扩充 |
| Judge 偏差与分数饱和 | 独立模型、人工校准、方差门槛、植入劣质答案、pairwise 随机顺序、固定版本 |
| 延迟优化损害完整性 | 质量非回退门槛优先于延迟收益 |
| 句柄缓存导致数据不一致 | 按 index mtime / 显式失效；no-diff 测试作为合并前置 |
| keyword 加上限改变召回 | 属 B 组，必须在可信基线之后；变更前后同时报告质量指标 |
| 延迟结论被噪声淹没 | 基线 N≥3 次、门槛取 2σ、区分后端 |
| 外部平台网络或配额失败 | 本地报告为主，adapter 失败降级并记录 notes |
| 私有资料泄露 | 默认关闭；优先自建 OTel collector；审批后才启用云端；脱敏、采样或完全不 trace |
| 依赖静默漂移（langsmith） | 显式声明并锁版本；CI 依赖快照检查 |
| 指标 schema 影响旧报告 | 增加兼容读取测试，必要时提供报告版本字段 |

回退单位保持小而明确：

- evidence schema 与旧字段并存一个兼容周期。
- tracing 通过配置整体关闭。
- 句柄缓存、keyword 上限、检索并行各自通过独立 feature flag 回退。
- 新 Judge 可退回确定性评分，但不得退回同模型静默自评。

## 13. 完成定义

只有同时满足以下条件，才能认为本轮评测体系改进完成：

- source-only 数据集显示「不可测」而非 `0.00`，看板主分不再误导。
- 存在 31/31 全部成功、重复 N≥3 次的可信基线，并记录了 σ 与后端类型。
- 31 个案例具备稳定 evidence（含 `document_key`）和 required facts。
- 至少一个多文档干扰集合和一组无答案案例可运行。
- 重切分后无需重新维护 chunk ID 标签。
- 检索、完整性、正确性、拒答和延迟指标语义明确，新指标不复用检索打分函数。
- 回答模型与 Judge 独立，并通过一致率、排序相关性和方差三项校准。
- 用户延迟和离线 Judge 延迟彻底分离；测不出的指标标注为不可测。
- 延迟改进量大于 2σ，且质量未越过退化线。
- 本地前端可以运行、查看和比较实验。
- OTel span 覆盖 §9.4 层级；LangSmith 若启用可追踪比较，若关闭本地系统完全可用。
- 相关单元、API、Worker、前端契约和全量测试全部通过。

## 14. 推荐的下一步

下一次代码实施对话只处理 **阶段 1A：测量诚实化**。理由：它是唯一能解锁「改进可被证明」的前置——在主分恒为 `0.00` 的情况下，任何检索或生成优化都无法在报告中体现。

阶段 1A 的四项改动全部位于测量层，互不冲突，且共同构成阶段 3 的前置，因此应在同一轮完成，避免对 `rag_eval.py` 和 `rag_evaluation_service.py` 反复动刀：

1. 主指标「不可测」语义（含前端渲染）。
2. `RagRetrievedItem` 补 `page`/`content`/`metadata`。
3. 429 重试与退避。
4. langsmith 依赖显式化。

不要在同一轮引入 evidence schema、性能修复、Judge 改造或任何外部平台。
