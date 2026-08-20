# 关键发现

- 项目为企业级 RAG 问答系统，技术栈包括 FastAPI、LangChain、PostgreSQL、Redis、Celery、FAISS/Milvus、Pytest、Docker。
- 已确认能力包括混合检索与 RRF、查询改写、来源片段、异步文档入库、RAG 评测、Prometheus 指标与 OpenTelemetry 链路追踪。
- 当前简历已有“字节跳动青训营”和“英蔻投资”两段实习条目；B 公司名称、准确日期与岗位名需由用户自行填写。
- 用户提供的两段项目经历已经详细覆盖 Skill/Memory/上下文压缩/多 Agent，以及多模态 RAG 的索引、检索与评测；新实习经历应强调企业级后端工程化与端到端交付，避免重复堆叠 RAG 术语。
- 代码证据确认：在线检索同时执行稠密向量召回与关键词召回，通过 RRF 融合，并支持规则重排、Top-K 和阈值配置。
- 对话服务基于持久化历史做 Query Rewrite；生成上下文带来源编号，并将来源片段、分数和 token usage 随回答写入消息记录。
- SSE 链路真实存在，事件包括 start、token、sources、done 和 error；流式完成后持久化回答与引用。
- 入库链路真实存在：文档状态 processing/indexed/failed，加载、切分、向量写入由 Celery 任务异步执行，并记录任务耗时和结果日志。
- FAISS/Milvus 通过统一后端协议与配置项切换，并共同支持新增、相似度检索、关键词检索、按文档删除和片段预览。
- 评测模块覆盖 Precision@K、Recall@K、Hit Rate、MRR、MAP、NDCG、来源命中、答案 groundedness、时延与 token 用量，并可选 LLM Judge。
- 可观测性包括请求 ID、结构化日志、HTTP/Celery 指标、Prometheus `/metrics` 及 FastAPI/SQLAlchemy/Celery 的 OpenTelemetry 接入。
- 最终文案采用 4 条：RAG 检索、文档向量化、对话与异步服务、质量工程；如版面不足，第四条作为可选删减项。
